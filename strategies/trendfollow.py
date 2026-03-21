from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class TrendFollowingStrategy(bt.Strategy):
    """
    Entry-timing strategy (buy and hold with smart entries):
    - Times entries based on technical confluence:
        * Trend filter: short SMA > long SMA and price > long SMA
        * Momentum confirmation: MACD > signal
        * Strength filter: RSI within a healthy range
        * Entry trigger: breakout above upper Bollinger Band
    - Invests 10% of available cash on each entry signal
    - NEVER sells - holds positions forever (like Buy & Hold, but with timed entries)
    - Allows multiple entries over time, scaling in gradually

    This strategy tests: "Can I beat Buy & Hold by timing my entries,
    while keeping the same long-term holding approach?"
    """

    params = dict(
        sma_fast=50,
        sma_slow=200,
        rsi_period=14,
        rsi_min=50,
        rsi_max=70,
        bb_period=20,
        bb_devfactor=2.0,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        # Exit params (currently unused - exits are disabled)
        stop_loss=0.05,  # 5%
        take_profit=0.15,  # 15%
        # Position sizing: 10% of available cash per entry
        cash_buffer=0.10,
        allow_fractional=True,
        printlog=True,
    )

    def __init__(self) -> None:
        self.order = None
        self.entry_price = None
        self.entry_date = None
        self.entry_size = None
        self.initial_cash = None  # Track starting cash

        # Series for portfolio metrics
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

        # Trade tracking
        self.trades = []  # List of completed trades (exits disabled, will be empty)
        self.entries = []  # List of entry points: {date, price, size, invested}

        # Indicators
        self.sma_fast = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.p.sma_fast
        )
        self.sma_slow = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.p.sma_slow
        )

        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)

        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )

        self.bbands = bt.indicators.BollingerBands(
            self.data.close,
            period=self.p.bb_period,
            devfactor=self.p.bb_devfactor,
        )

        # Useful crossover indicator
        self.macd_cross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

    def log(self, txt: str) -> None:
        if self.p.printlog:
            dt = self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()} | {txt}")

    def next(self) -> None:
        dt = self.datas[0].datetime.date(0)
        close = float(self.data.close[0])

        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        # Capture initial cash on first bar
        if self.initial_cash is None:
            self.initial_cash = cash

        # collect metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # avoid placing new orders if one is pending
        if self.order:
            return

        # =========================
        # ENTRY (allows multiple entries over time - scales in gradually)
        # =========================
        trend_ok = close > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]
        momentum_ok = self.macd.macd[0] > self.macd.signal[0]
        rsi_ok = self.p.rsi_min <= self.rsi[0] <= self.p.rsi_max

        # Breakout condition: close above upper Bollinger Band
        breakout_ok = close > self.bbands.top[0]

        if trend_ok and momentum_ok and rsi_ok and breakout_ok:
            # Invest 10% of current cash on each signal
            invest = cash * self.p.cash_buffer
            size = invest / close

            if not self.p.allow_fractional:
                size = int(size)

            if size > 0:
                self.log(
                    f"BUY SIGNAL (10% of cash = ${invest:,.2f}) | Close: {close:.2f} | "
                    f"SMA{self.p.sma_fast}: {self.sma_fast[0]:.2f} | "
                    f"SMA{self.p.sma_slow}: {self.sma_slow[0]:.2f} | "
                    f"RSI: {self.rsi[0]:.2f} | "
                    f"MACD: {self.macd.macd[0]:.4f} > Signal: {self.macd.signal[0]:.4f}"
                )
                self.order = self.buy(size=size)

        # =========================
        # EXIT (DISABLED - buy and hold approach)
        # =========================
        # Exits are commented out to test "time the entry, hold forever" strategy
        # This tests whether smart entry timing can beat Buy & Hold
        # while keeping the same long-term holding discipline.

        # Original exit logic (disabled):
        # if self.position:
        #     if self.entry_price is None:
        #         return
        #
        #     stop_price = self.entry_price * (1.0 - self.p.stop_loss)
        #     take_price = self.entry_price * (1.0 + self.p.take_profit)
        #
        #     stop_hit = close <= stop_price
        #     take_hit = close >= take_price
        #
        #     trend_lost = (
        #         close < self.sma_fast[0]
        #         or close < self.sma_slow[0]
        #         or self.sma_fast[0] < self.sma_slow[0]
        #     )
        #
        #     macd_bearish = self.macd.macd[0] < self.macd.signal[0]
        #
        #     if stop_hit:
        #         self.log(f"SELL SIGNAL | STOP LOSS | Close: {close:.2f}")
        #         self.order = self.sell(size=self.position.size)
        #
        #     elif take_hit:
        #         self.log(f"SELL SIGNAL | TAKE PROFIT | Close: {close:.2f}")
        #         self.order = self.sell(size=self.position.size)
        #
        #     elif trend_lost:
        #         self.log(f"SELL SIGNAL | TREND LOST | Close: {close:.2f}")
        #         self.order = self.sell(size=self.position.size)
        #
        #     elif macd_bearish:
        #         self.log(f"SELL SIGNAL | MACD BEARISH | Close: {close:.2f}")
        #         self.order = self.sell(size=self.position.size)

    def notify_order(self, order: bt.Order) -> None:
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                # Record entry (we never sell, so just track buys)
                entry_price = float(order.executed.price)
                entry_date = self.datas[0].datetime.date(0)
                entry_size = float(order.executed.size)
                invested = entry_price * entry_size

                self.entries.append({
                    'date': entry_date,
                    'price': entry_price,
                    'size': entry_size,
                    'invested': invested,
                })

                # Keep last entry info for reporting
                self.entry_price = entry_price
                self.entry_date = entry_date
                self.entry_size = entry_size

            # No sell handling - exits are disabled

        self.order = None

    def stop(self) -> None:
        """Print entry summary and plot portfolio breakdown at end of backtest."""
        # Print entry summary
        print("\n" + "="*80)
        print("TRENDFOLLOWING STRATEGY - ENTRY TIMING SUMMARY")
        print("(Buy and hold with timed entries - no exits)")
        print("="*80)

        # Cash deployment stats
        initial_cash = self.initial_cash if self.initial_cash is not None else 0
        final_cash = float(self.broker.getcash())
        final_value = float(self.broker.getvalue())

        print(f"\nCASH DEPLOYMENT:")
        print(f"  Initial Cash:        ${initial_cash:>13,.2f}")

        if not self.entries:
            print(f"  Final Cash:          ${final_cash:>13,.2f}")
            print(f"  Total Invested:      ${0:>13,.2f}")
            print(f"  Deployed:            {0:>12.1f}%")
            print(f"  Remaining in Cash:   {100:>12.1f}%")
            print("\nNo entries made (likely insufficient data for indicator warm-up).")
        else:
            num_entries = len(self.entries)
            total_invested = sum(e['invested'] for e in self.entries)
            pct_deployed = (total_invested / initial_cash * 100) if initial_cash > 0 else 0
            pct_remaining = (final_cash / initial_cash * 100) if initial_cash > 0 else 0

            print(f"  Final Cash:          ${final_cash:>13,.2f}")
            print(f"  Total Invested:      ${total_invested:>13,.2f}")
            print(f"  Deployed:            {pct_deployed:>12.1f}%")
            print(f"  Remaining in Cash:   {pct_remaining:>12.1f}%")

            avg_invested = total_invested / num_entries if num_entries > 0 else 0
            avg_price = sum(e['price'] for e in self.entries) / num_entries if num_entries > 0 else 0

            # Current position value
            current_price = float(self.datas[0].close[0])
            total_shares = sum(e['size'] for e in self.entries)
            current_value = total_shares * current_price
            total_gain = current_value - total_invested
            total_gain_pct = (total_gain / total_invested * 100) if total_invested > 0 else 0

            print(f"\nENTRY STATISTICS:")
            print(f"  Total Entries: {num_entries}")
            print(f"  Average per Entry: ${avg_invested:,.2f}")
            print(f"  Average Entry Price: ${avg_price:.2f}")

            print(f"\nPOSITION VALUE:")
            print(f"  Total Shares Accumulated: {total_shares:.4f}")
            print(f"  Current Price: ${current_price:.2f}")
            print(f"  Current Position Value: ${current_value:,.2f}")
            print(f"  Unrealized P&L: ${total_gain:+,.2f} ({total_gain_pct:+.2f}%)")

            print(f"\nPORTFOLIO BREAKDOWN:")
            print(f"  Cash:     ${final_cash:>13,.2f}  ({final_cash/final_value*100:>5.1f}%)")
            print(f"  Position: ${current_value:>13,.2f}  ({current_value/final_value*100:>5.1f}%)")
            print(f"  Total:    ${final_value:>13,.2f}")

            # Compare to Buy & Hold deployment
            print(f"\n  Note: Buy & Hold deploys ~99.5% on day 1")
            print(f"        TrendFollowing deployed {pct_deployed:.1f}% over {num_entries} entries")

            # Entry-by-entry breakdown
            print(f"\n{'-'*80}")
            print("ENTRY HISTORY")
            print(f"{'-'*80}")
            print(f"{'#':<4} {'Date':<12} {'Price':>10} {'Shares':>12} {'Invested':>14} {'% of Cash':>11}")
            print(f"{'-'*80}")

            for i, entry in enumerate(self.entries, 1):
                # Show what % this was (approximately 10%)
                pct_marker = "~10%"
                print(f"{i:<4} {str(entry['date']):<12} "
                      f"${entry['price']:>9.2f} {entry['size']:>12.4f} "
                      f"${entry['invested']:>13.2f} {pct_marker:>11}")

            print(f"{'-'*80}")
            print(f"{'TOTAL':<17} {'':<10} {total_shares:>12.4f} ${total_invested:>13.2f}")

        print("="*80 + "\n")

        # Plot portfolio breakdown
        plt.figure(figsize=(10, 6))

        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        num_entries_text = f"{len(self.entries)} entries" if self.entries else "no entries"
        plt.title(f"TrendFollowing (Entry Timing Only) - Portfolio Breakdown ({num_entries_text})")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.show()
        # plt.savefig("reports/trendfollowing_portfolio.png")
        # plt.close()
