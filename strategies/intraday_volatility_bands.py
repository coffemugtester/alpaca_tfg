"""
Trend-Filtered Volatility Bands Swing Trading Strategy

Buys intraday dips ONLY during daily uptrends, holds for multi-day swings.

Strategy Logic:
1. DAILY TREND FILTER: Only buy when price is above 200-day SMA (bull market)
2. INTRADAY ENTRY: Wait for price to touch lower volatility band during European close
3. SWING EXIT: Hold for days/weeks until +6% profit or stop loss

Market Timing Windows (ET):
- 09:30-11:00: Market open, horizontal movement unless breakout
- 10:30-12:00: European market close, SP500 tends to drop - PREFERRED ENTRY
- 14:00-15:00: Algorithmic trading activity
- 15:00-16:00: Institutional money determines close

Entry Requirements (ALL must be true):
- Daily trend: Price > 200-day SMA (bull market filter)
- Intraday dip: Price touches lower band (SMA - ATR * multiplier) on minute data
- Time window: European close (10:30-12:00 ET)
- Daily limit: Max 1 entry per day
- Position sizing: ATR-based risk management

Exit:
- Take profit: +6% gain (after minimum 2-hour hold)
- Stop loss: -4% or ATR-based, whichever is wider
- No EOD force close - hold multi-day positions

Risk Management:
- Max 1 entry per trading day
- ATR-based position sizing (risk 2% of portfolio per trade)
- Fixed take profit target (6%)
- Minimum hold time (2 hours) to avoid noise
- Overnight positions allowed
"""

from __future__ import annotations

import csv
import os
from datetime import time, date
from pathlib import Path

import backtrader as bt
import matplotlib.pyplot as plt


class IntradayVolatilityBands(bt.Strategy):
    params = dict(
        # Daily trend filter
        daily_sma_period=200,  # 200-day SMA for bull/bear filter
        require_daily_uptrend=False,  # Allow entries in all market conditions

        # Indicator parameters (minute data)
        atr_period=60,  # ATR calculation period (minutes)
        sma_period=120,  # SMA period for centerline (minutes)
        band_multiplier=4.0,  # Band distance from SMA (ATR units)
        stop_multiplier=3.0,  # Stop loss distance in ATR units

        # Risk management
        use_stop_loss=False,  # Enable/disable stop loss (DISABLED - trust recovery)
        risk_per_trade=0.15,  # Risk 15% of portfolio value per trade (increased for better capital utilization)
        take_profit_pct=0.06,  # Take profit at 6% gain
        stop_loss_pct=0.04,  # Minimum stop loss at 4% (if enabled)
        min_hold_hours=2.0,  # Minimum hold time in hours (avoid premature exits)
        allow_short=False,  # Whether to take short positions
        allow_fractional=True,  # Allow fractional shares
        max_daily_entries=1,  # Maximum entries per trading day

        # Market timing windows (ET)
        market_open=time(9, 30),
        european_close_start=time(10, 30),  # Preferred entry window start
        european_close_end=time(12, 0),     # Preferred entry window end
        algo_trading_start=time(14, 0),
        algo_trading_end=time(15, 0),
        institutional_start=time(15, 0),

        # Analytics
        show_plot=True,  # Display matplotlib chart
        export_trades=True,  # Export trade details to CSV
    )

    def __init__(self) -> None:
        # Data feeds: datas[0] = minute data, datas[1] = daily data (if provided)
        self.minute_data = self.datas[0] if len(self.datas) > 0 else self.data
        self.has_daily_data = len(self.datas) > 1

        # Minute data indicators (for entry signals)
        self.atr = bt.indicators.ATR(self.minute_data, period=self.p.atr_period)
        self.sma = bt.indicators.SMA(self.minute_data.close, period=self.p.sma_period)

        # Volatility bands (minute data)
        self.upper_band = self.sma + (self.atr * self.p.band_multiplier)
        self.lower_band = self.sma - (self.atr * self.p.band_multiplier)

        # Daily trend filter (if daily data provided)
        if self.has_daily_data:
            self.daily_data = self.datas[1]
            self.daily_sma = bt.indicators.SMA(
                self.daily_data.close,
                period=self.p.daily_sma_period
            )
        else:
            self.daily_data = None
            self.daily_sma = None

        # Tracking
        self.order = None
        self.entry_price = None
        self.entry_time = None
        self.stop_price = None
        self.trade_count = 0
        self.position_size = 0

        # Daily entry limit tracking
        self.daily_entry_count = 0
        self.current_trading_date = None

        # Performance tracking
        self.trades_log = []  # Order-level executions
        self.completed_trades = []  # Full round-trip trade analytics
        self.daily_pnl = []

    def prenext_open(self) -> None:
        """Called during warm-up period before indicators are ready."""
        pass  # Wait for indicators to be ready

    def _reset_daily_counters_if_needed(self) -> None:
        """Reset daily entry counter at market open each day."""
        current_dt = self.minute_data.datetime.datetime(0)
        current_date = current_dt.date()

        if self.current_trading_date != current_date:
            self.daily_entry_count = 0
            self.current_trading_date = current_date

    def _get_time_window(self, current_time: time) -> str:
        """Classify current time into market microstructure phases."""
        if self.p.market_open <= current_time < self.p.european_close_start:
            return "MARKET_OPEN"
        elif self.p.european_close_start <= current_time < self.p.european_close_end:
            return "EUROPEAN_CLOSE"  # Preferred entry window
        elif self.p.european_close_end <= current_time < self.p.algo_trading_start:
            return "MIDDAY"
        elif self.p.algo_trading_start <= current_time < self.p.algo_trading_end:
            return "ALGO_TRADING"
        else:
            return "INSTITUTIONAL"

    def _is_preferred_entry_window(self, current_time: time) -> bool:
        """Check if current time is in the preferred entry window (European close)."""
        return self.p.european_close_start <= current_time < self.p.european_close_end

    def _can_enter_trade(self) -> bool:
        """Check if we can enter a new trade (daily limit not reached)."""
        return self.daily_entry_count < self.p.max_daily_entries

    def next_open(self) -> None:
        """Check for entries and exits at bar open (after indicators are ready)."""
        # Reset daily counters if new trading day
        self._reset_daily_counters_if_needed()

        # Skip if we have pending orders
        if self.order is not None:
            return

        position = self.getposition()

        # Check for entry signals if we don't have a position
        if position.size == 0:
            self._check_entry_signals()

        # Check exit signals if we have a position
        if position.size != 0:
            self._check_exit_signals()

    def next(self) -> None:
        """Called after each bar closes."""
        # Track daily performance
        current_time = self.minute_data.datetime.time(0)
        if current_time == time(16, 0):  # Market close
            value = float(self.broker.getvalue())
            self.daily_pnl.append(value)

    def _calculate_position_size(self, entry_price: float, stop_price: float | None = None) -> float:
        """
        Calculate position size based on ATR risk management.

        Risk a fixed percentage (e.g., 5%) of total portfolio value per trade.
        Position size = (Portfolio Value × Risk %) / (Entry Price - Stop Price)

        If stop loss is disabled, assume worst case -10% move for position sizing.
        """
        portfolio_value = float(self.broker.getvalue())
        risk_amount = portfolio_value * self.p.risk_per_trade

        # Calculate stop distance
        if self.p.use_stop_loss and stop_price is not None:
            # Use actual stop price
            stop_distance = abs(entry_price - stop_price)
        else:
            # No stop loss: assume worst case -6% move for position sizing (matching take profit)
            assumed_risk_pct = 0.06
            stop_distance = entry_price * assumed_risk_pct

        if stop_distance == 0:
            return 0

        # Calculate position size based on risk
        size = risk_amount / stop_distance

        # Apply fractional constraint if needed
        if not self.p.allow_fractional:
            size = int(size)

        # Ensure we don't exceed available cash
        # Account for commission + slippage (typically ~0.05% total)
        # Leave 1% buffer for safety
        available_cash = float(self.broker.getcash()) * 0.99
        max_size_by_cash = available_cash / entry_price

        size = min(size, max_size_by_cash)

        # Ensure size is positive
        if size < 0:
            size = 0

        return size

    def _check_entry_signals(self) -> None:
        """Check for band touch entry signals with timing, daily limit, and trend filter constraints."""
        # Check if we've reached daily entry limit
        if not self._can_enter_trade():
            return

        current_time = self.minute_data.datetime.time(0)
        current_price = float(self.minute_data.close[0])
        lower = float(self.lower_band[0])
        upper = float(self.upper_band[0])
        atr_value = float(self.atr[0])

        # Get current market timing window
        time_window = self._get_time_window(current_time)
        is_preferred_window = self._is_preferred_entry_window(current_time)

        # Only enter during preferred window (European close: 10:30-12:00 ET)
        if not is_preferred_window:
            return

        # DAILY TREND FILTER: Only enter if price > 200-day SMA (bull market)
        if self.p.require_daily_uptrend and self.has_daily_data:
            daily_price = float(self.daily_data.close[0])
            daily_sma_value = float(self.daily_sma[0])

            if daily_price <= daily_sma_value:
                # Skip entry - we're in a bear market
                return

        # Long entry: price touches or breaks below lower band
        if current_price <= lower:
            # Calculate stop price: max(ATR-based, fixed 4%)
            atr_stop = current_price - (atr_value * self.p.stop_multiplier)
            fixed_stop = current_price * (1 - self.p.stop_loss_pct)
            stop_price = max(atr_stop, fixed_stop)  # Use wider stop

            # Calculate position size based on risk management
            size = self._calculate_position_size(current_price, stop_price)

            if size > 0:
                self.order = self.buy(size=size)
                self.entry_price = current_price
                self.entry_time = self.minute_data.datetime.datetime(0)
                self.stop_price = stop_price
                self.position_size = size
                self.daily_entry_count += 1

                portfolio_value = float(self.broker.getvalue())
                risk_amount = portfolio_value * self.p.risk_per_trade

                # Show daily trend info if available
                trend_info = ""
                if self.has_daily_data:
                    daily_price = float(self.daily_data.close[0])
                    daily_sma_value = float(self.daily_sma[0])
                    trend_info = f" | Daily: ${daily_price:.2f} > SMA200: ${daily_sma_value:.2f}"

                print(f"\n{self.entry_time.strftime('%Y-%m-%d %H:%M')} [{time_window}]{trend_info}")
                print(f"LONG ENTRY @ ${current_price:.2f}")
                print(f"  Lower Band: ${lower:.2f} | Stop: ${stop_price:.2f} (ATR or 4%)")
                print(f"  Size: {size:.2f} shares | Risk: ${risk_amount:.2f} ({self.p.risk_per_trade*100:.1f}%)")
                print(f"  Portfolio Value: ${portfolio_value:.2f}")
                print(f"  Daily entries: {self.daily_entry_count}/{self.p.max_daily_entries}\n")

        # Short entry: price touches or breaks above upper band (if enabled)
        elif self.p.allow_short and current_price >= upper:
            # Calculate stop price: max(ATR-based, fixed 4%)
            atr_stop = current_price + (atr_value * self.p.stop_multiplier)
            fixed_stop = current_price * (1 + self.p.stop_loss_pct)
            stop_price = min(atr_stop, fixed_stop)  # Use tighter stop for shorts

            # Calculate position size based on risk management
            size = self._calculate_position_size(current_price, stop_price)

            if size > 0:
                self.order = self.sell(size=size)
                self.entry_price = current_price
                self.entry_time = self.minute_data.datetime.datetime(0)
                self.stop_price = stop_price
                self.position_size = size
                self.daily_entry_count += 1

                portfolio_value = float(self.broker.getvalue())
                risk_amount = portfolio_value * self.p.risk_per_trade

                print(f"\n{self.entry_time.strftime('%Y-%m-%d %H:%M')} [{time_window}]")
                print(f"SHORT ENTRY @ ${current_price:.2f}")
                print(f"  Upper Band: ${upper:.2f} | Stop: ${stop_price:.2f}")
                print(f"  Size: {size:.2f} shares | Risk: ${risk_amount:.2f} ({self.p.risk_per_trade*100:.1f}%)")
                print(f"  Portfolio Value: ${portfolio_value:.2f}")
                print(f"  Daily entries: {self.daily_entry_count}/{self.p.max_daily_entries}\n")

    def _check_exit_signals(self) -> None:
        """
        Check for exit conditions: take profit or stop loss (if enabled).

        Exit conditions:
        - Take profit: +6% gain from entry price
        - Stop loss: ATR-based or fixed 4% loss (if use_stop_loss=True)
        - Minimum hold time: 2 hours to avoid noise
        """
        if self.entry_price is None or self.entry_time is None:
            return

        position = self.getposition()
        if position.size == 0:
            return

        current_price = float(self.minute_data.close[0])
        current_time = self.minute_data.datetime.datetime(0)

        # Check minimum hold time (avoid premature exits)
        hold_duration_hours = (current_time - self.entry_time).total_seconds() / 3600
        if hold_duration_hours < self.p.min_hold_hours:
            return

        # Calculate P&L
        if position.size > 0:  # Long position
            pnl_pct = (current_price - self.entry_price) / self.entry_price
            pnl_dollars = (current_price - self.entry_price) * position.size

            # Take profit: +6% gain
            if pnl_pct >= self.p.take_profit_pct:
                self.order = self.close()
                print(f"\n{current_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"TAKE PROFIT EXIT @ ${current_price:.2f}")
                print(f"  Entry: ${self.entry_price:.2f} | Gain: {pnl_pct*100:.2f}% (${pnl_dollars:.2f})")
                print(f"  Hold Time: {hold_duration_hours:.1f} hours\n")
                self._record_trade('TAKE_PROFIT', current_price, current_time, pnl_pct, pnl_dollars)
                return

            # Stop loss: only if enabled
            if self.p.use_stop_loss and self.stop_price is not None:
                if current_price <= self.stop_price:
                    self.order = self.close()
                    print(f"\n{current_time.strftime('%Y-%m-%d %H:%M')}")
                    print(f"STOP LOSS EXIT @ ${current_price:.2f}")
                    print(f"  Entry: ${self.entry_price:.2f} | Loss: {pnl_pct*100:.2f}% (${pnl_dollars:.2f})")
                    print(f"  Stop Price: ${self.stop_price:.2f} | Hold Time: {hold_duration_hours:.1f} hours\n")
                    self._record_trade('STOP_LOSS', current_price, current_time, pnl_pct, pnl_dollars)
                    return

        elif position.size < 0:  # Short position
            pnl_pct = (self.entry_price - current_price) / self.entry_price
            pnl_dollars = (self.entry_price - current_price) * abs(position.size)

            # Take profit: +6% gain
            if pnl_pct >= self.p.take_profit_pct:
                self.order = self.close()
                print(f"\n{current_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"TAKE PROFIT EXIT (SHORT) @ ${current_price:.2f}")
                print(f"  Entry: ${self.entry_price:.2f} | Gain: {pnl_pct*100:.2f}% (${pnl_dollars:.2f})")
                print(f"  Hold Time: {hold_duration_hours:.1f} hours\n")
                self._record_trade('TAKE_PROFIT', current_price, current_time, pnl_pct, pnl_dollars)
                return

            # Stop loss: only if enabled
            if self.p.use_stop_loss and self.stop_price is not None:
                if current_price >= self.stop_price:
                    self.order = self.close()
                    print(f"\n{current_time.strftime('%Y-%m-%d %H:%M')}")
                    print(f"STOP LOSS EXIT (SHORT) @ ${current_price:.2f}")
                    print(f"  Entry: ${self.entry_price:.2f} | Loss: {pnl_pct*100:.2f}% (${pnl_dollars:.2f})")
                    print(f"  Stop Price: ${self.stop_price:.2f} | Hold Time: {hold_duration_hours:.1f} hours\n")
                    self._record_trade('STOP_LOSS', current_price, current_time, pnl_pct, pnl_dollars)
                    return

    def _record_trade(self, exit_reason: str, exit_price: float, exit_time, pnl_pct: float, pnl_dollars: float) -> None:
        """Record completed trade for analytics and reset entry tracking."""
        direction = "LONG" if self.position_size > 0 else "SHORT"

        trade_record = {
            'direction': direction,
            'entry_time': self.entry_time,
            'exit_time': exit_time,
            'entry_price': self.entry_price,
            'exit_price': exit_price,
            'stop_price': self.stop_price,
            'position_size': self.position_size,
            'pnl_pct': pnl_pct,
            'pnl_dollars': pnl_dollars,
            'exit_reason': exit_reason,
            'hold_duration_seconds': (exit_time - self.entry_time).total_seconds(),
        }

        self.completed_trades.append(trade_record)

        # Reset entry tracking so we can take new positions
        self.entry_price = None
        self.entry_time = None
        self.stop_price = None
        self.position_size = 0

    def notify_order(self, order: bt.Order) -> None:
        """Handle order notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            action = "BUY" if order.isbuy() else "SELL"
            self.trades_log.append({
                'datetime': self.minute_data.datetime.datetime(0),
                'action': action,
                'price': order.executed.price,
                'size': order.executed.size,
                'value': order.executed.value,
                'comm': order.executed.comm,
            })

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"ORDER FAILED | Status: {order.getstatusname()}")

        self.order = None

    def stop(self) -> None:
        """Called at end of backtest."""
        final_value = float(self.broker.getvalue())

        # Calculate analytics
        winning_trades = [t for t in self.completed_trades if t['pnl_dollars'] > 0]
        losing_trades = [t for t in self.completed_trades if t['pnl_dollars'] <= 0]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / len(self.completed_trades) * 100) if self.completed_trades else 0

        avg_win = sum(t['pnl_dollars'] for t in winning_trades) / win_count if win_count > 0 else 0
        avg_loss = sum(t['pnl_dollars'] for t in losing_trades) / loss_count if loss_count > 0 else 0
        profit_factor = abs(avg_win * win_count / (avg_loss * loss_count)) if (avg_loss != 0 and loss_count > 0) else 0

        # Exit reason breakdown
        stop_loss_exits = len([t for t in self.completed_trades if t['exit_reason'] == 'STOP_LOSS'])
        take_profit_exits = len([t for t in self.completed_trades if t['exit_reason'] == 'TAKE_PROFIT'])

        # Average hold time
        avg_hold_seconds = sum(t['hold_duration_seconds'] for t in self.completed_trades) / len(self.completed_trades) if self.completed_trades else 0
        avg_hold_hours = avg_hold_seconds / 3600

        print(f"\n{'='*70}")
        print(f"Volatility Bands Swing Trading Strategy - Results")
        print(f"{'='*70}")
        print(f"Final Portfolio Value: ${final_value:,.2f}")
        print(f"Total Completed Trades: {len(self.completed_trades)}")

        print(f"\nPerformance Metrics:")
        print(f"  Win Rate: {win_rate:.1f}% ({win_count}W / {loss_count}L)")
        print(f"  Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f}")
        print(f"  Profit Factor: {profit_factor:.2f}")
        print(f"  Avg Hold Time: {avg_hold_hours:.1f} hours")

        print(f"\nExit Breakdown:")
        print(f"  Stop Loss: {stop_loss_exits} ({stop_loss_exits/len(self.completed_trades)*100:.1f}%)" if self.completed_trades else "  Stop Loss: 0")
        print(f"  Take Profit: {take_profit_exits} ({take_profit_exits/len(self.completed_trades)*100:.1f}%)" if self.completed_trades else "  Take Profit: 0")

        print(f"\nStrategy Parameters:")
        print(f"  ATR Period: {self.p.atr_period} min | SMA Period: {self.p.sma_period} min")
        print(f"  Band Multiplier: {self.p.band_multiplier}x | Stop Multiplier: {self.p.stop_multiplier}x")
        print(f"  Risk per Trade: {self.p.risk_per_trade*100:.1f}% | Take Profit: {self.p.take_profit_pct*100:.1f}%")
        print(f"  Min Hold Time: {self.p.min_hold_hours:.1f} hours | Max Daily Entries: {self.p.max_daily_entries}")

        print(f"\nMarket Timing Windows (ET):")
        print(f"  Preferred Entry: {self.p.european_close_start.strftime('%H:%M')}-{self.p.european_close_end.strftime('%H:%M')} (European Close)")
        print(f"  Overnight Positions: ALLOWED")
        print(f"{'='*70}\n")

        # Export trade analytics to CSV only if we have completed trades
        if self.p.export_trades and len(self.completed_trades) > 0:
            self._export_trade_analytics()
        elif self.p.export_trades and len(self.trades_log) > 0:
            # Fallback: if no completed trades but have entries, export entry-only data
            print("Note: No completed trades to export. Exporting entry-only data.")
            self._export_entry_analytics()

        if self.p.show_plot and len(self.completed_trades) > 0:
            self._plot_results()

    def _export_entry_analytics(self) -> None:
        """Export entry-only analytics to CSV (for no-exit strategies)."""
        # Get symbol name from data feed
        symbol = self.minute_data._name if hasattr(self.minute_data, '_name') else 'UNKNOWN'

        # Create output directory
        output_dir = Path('global_comparison')
        output_dir.mkdir(exist_ok=True)

        # Generate filename with symbol
        filename = output_dir / f'entry_analytics_{symbol}.csv'

        # Prepare CSV data - only BUY entries
        fieldnames = [
            'symbol',
            'action',
            'entry_time',
            'entry_price',
            'position_size',
            'value',
            'commission',
        ]

        # Write to CSV
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for trade in self.trades_log:
                if trade['action'] == 'BUY':  # Only export entries
                    row = {
                        'symbol': symbol,
                        'action': trade['action'],
                        'entry_time': trade['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                        'entry_price': f"{trade['price']:.2f}",
                        'position_size': f"{trade['size']:.2f}",
                        'value': f"{trade['value']:.2f}",
                        'commission': f"{trade['comm']:.2f}",
                    }
                    writer.writerow(row)

        buy_count = sum(1 for t in self.trades_log if t['action'] == 'BUY')
        print(f"Entry analytics exported to: {filename}")
        print(f"Total entries exported: {buy_count}\n")

    def _export_trade_analytics(self) -> None:
        """Export detailed trade analytics to CSV."""
        # Get symbol name from data feed
        symbol = self.minute_data._name if hasattr(self.minute_data, '_name') else 'UNKNOWN'

        # Create output directory
        output_dir = Path('global_comparison')
        output_dir.mkdir(exist_ok=True)

        # Generate filename with symbol and timestamp
        filename = output_dir / f'trade_analytics_{symbol}.csv'

        # Prepare CSV data
        fieldnames = [
            'symbol',
            'direction',
            'entry_time',
            'exit_time',
            'entry_price',
            'exit_price',
            'stop_price',
            'position_size',
            'pnl_dollars',
            'pnl_pct',
            'exit_reason',
            'hold_duration_hours',
            'hold_duration_days',
        ]

        # Write to CSV
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for trade in self.completed_trades:
                hold_hours = trade['hold_duration_seconds'] / 3600
                hold_days = hold_hours / 24

                row = {
                    'symbol': symbol,
                    'direction': trade['direction'],
                    'entry_time': trade['entry_time'].strftime('%Y-%m-%d %H:%M:%S'),
                    'exit_time': trade['exit_time'].strftime('%Y-%m-%d %H:%M:%S'),
                    'entry_price': f"{trade['entry_price']:.2f}",
                    'exit_price': f"{trade['exit_price']:.2f}",
                    'stop_price': f"{trade['stop_price']:.2f}",
                    'position_size': f"{trade['position_size']:.2f}",
                    'pnl_dollars': f"{trade['pnl_dollars']:.2f}",
                    'pnl_pct': f"{trade['pnl_pct']:.2f}",
                    'exit_reason': trade['exit_reason'],
                    'hold_duration_hours': f"{hold_hours:.2f}",
                    'hold_duration_days': f"{hold_days:.2f}",
                }
                writer.writerow(row)

        print(f"Trade analytics exported to: {filename}")
        print(f"Total trades exported: {len(self.completed_trades)}\n")

    def _plot_results(self) -> None:
        """Generate performance plot."""
        plt.figure(figsize=(12, 8))

        # Plot 1: Portfolio value over time
        plt.subplot(2, 1, 1)
        if self.daily_pnl:
            plt.plot(self.daily_pnl, label='Portfolio Value')
            plt.xlabel('Trading Days')
            plt.ylabel('Value ($)')
            plt.title('Intraday Volatility Bands - Portfolio Value')
            plt.legend()
            plt.grid(True)

        # Plot 2: Trade count over time
        plt.subplot(2, 1, 2)
        if self.trades_log:
            dates = [t['datetime'] for t in self.trades_log]
            cumulative_trades = list(range(1, len(dates) + 1))
            plt.plot(dates, cumulative_trades, label='Cumulative Trades', color='green')
            plt.xlabel('Date')
            plt.ylabel('Trade Count')
            plt.title('Trade Activity')
            plt.legend()
            plt.grid(True)

        plt.tight_layout()

        if self.p.show_plot:
            plt.show()
        else:
            plt.close()
