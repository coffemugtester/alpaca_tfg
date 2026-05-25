from __future__ import annotations

from datetime import date

import backtrader as bt
import matplotlib.pyplot as plt

from strategies.base_strategy import TradeTrackingMixin


class TacticalVolumeDCA(TradeTrackingMixin, bt.Strategy):
    """
    Volume-Confirmed Correction DCA Strategy.

    Combines daily Bollinger Band correction detection with intraday volume
    spike confirmation for precise entry timing.

    Logic:
    - Simulates a DCA investor with fixed monthly contribution.
    - Each month, one monthly contribution is added to accumulated reserve.
    - Reserve is deployed only when:
        1. Daily price breaks below middle Bollinger Band (dip detected)
        2. Intraday volume spike detected (> 2x average volume)
        3. Haven't bought yet this month
    - No selling logic - accumulation only.

    Data feeds:
    - self.datas[0] = Minute bars (primary feed for volume spike detection)
    - self.datas[1] = Daily bars (for Bollinger Band correction filter)
    """

    params = dict(
        # Daily Bollinger Band parameters (correction detection)
        daily_bb_period=20,
        daily_bb_devfactor=2.0,
        # Intraday volume parameters (entry timing)
        volume_sma_period=60,  # 60-minute average volume
        volume_threshold=2.0,  # Volume spike = 2x average
        # Position sizing
        max_exposure=0.995,
        min_order_cash=250.0,
        show_plot=True,
    )

    def __init__(self) -> None:
        # Initialize trade tracking
        self._init_trade_tracking()

        # Data feeds
        self.minute_data = self.datas[0]  # Primary feed (minute bars)
        self.has_daily_data = len(self.datas) > 1

        # Minute indicators (volume spike detection)
        self.minute_volume_sma = bt.ind.SMA(
            self.minute_data.volume,
            period=self.p.volume_sma_period,
        )

        # Daily indicators (correction detection)
        if self.has_daily_data:
            self.daily_data = self.datas[1]
            self.daily_close = self.daily_data.close

            self.daily_bbands = bt.ind.BollingerBands(
                self.daily_close,
                period=self.p.daily_bb_period,
                devfactor=self.p.daily_bb_devfactor,
            )

        # Reserve tracking
        self.initial_cash: float | None = None
        self.start_year_month: tuple[int, int] | None = None
        self.end_year_month: tuple[int, int] | None = None
        self.total_months: int | None = None
        self.monthly_contribution: float | None = None

        self.current_month: tuple[int, int] | None = None
        self.accumulated_reserve: float = 0.0
        self.last_buy_month: tuple[int, int] | None = None
        self.buy_count: int = 0

        # Analytics tracking
        self.dates: list[date] = []
        self.cash: list[float] = []
        self.position_value: list[float] = []
        self.total_value: list[float] = []
        self.reserve_history: list[float] = []
        self.exposure_pct: list[float] = []

    def start(self) -> None:
        self.initial_cash = self.broker.getcash()

        # Use minute data to determine date range
        data_dates = [
            bt.num2date(self.minute_data.datetime.array[i]).date()
            for i in range(len(self.minute_data.datetime.array))
        ]

        start_date = data_dates[0]
        end_date = data_dates[-1]

        self.start_year_month = (start_date.year, start_date.month)
        self.end_year_month = (end_date.year, end_date.month)

        self.total_months = (
            self._months_between(self.start_year_month, self.end_year_month) + 1
        )

        deployable_cash = self.initial_cash * self.p.max_exposure
        self.monthly_contribution = deployable_cash / self.total_months

        print(f"[TacticalVolumeDCA] Initial cash: ${self.initial_cash:,.2f}")
        print(f"[TacticalVolumeDCA] Start month: {self.start_year_month}")
        print(f"[TacticalVolumeDCA] End month: {self.end_year_month}")
        print(f"[TacticalVolumeDCA] Total months: {self.total_months}")
        print(
            f"[TacticalVolumeDCA] Monthly contribution: "
            f"${self.monthly_contribution:,.2f}"
        )

    def _months_between(
        self,
        start_ym: tuple[int, int],
        end_ym: tuple[int, int],
    ) -> int:
        start_year, start_month = start_ym
        end_year, end_month = end_ym
        return (end_year - start_year) * 12 + (end_month - start_month)

    def _current_year_month(self) -> tuple[int, int]:
        dt = self.minute_data.datetime.date(0)
        return (dt.year, dt.month)

    def _process_monthly_contribution(self) -> None:
        ym = self._current_year_month()

        if self.current_month == ym:
            return

        self.current_month = ym

        if self.monthly_contribution is None:
            return

        self.accumulated_reserve += self.monthly_contribution

    def _already_bought_this_month(self) -> bool:
        return self.last_buy_month == self._current_year_month()

    def _portfolio_value(self) -> float:
        return self.broker.getvalue()

    def _cash(self) -> float:
        return self.broker.getcash()

    def _invested_value(self) -> float:
        return self._portfolio_value() - self._cash()

    def _current_exposure_pct(self) -> float:
        value = self._portfolio_value()
        if value <= 0:
            return 0.0
        return self._invested_value() / value

    def _max_allowed_invested(self) -> float:
        return self.initial_cash * self.p.max_exposure  # type: ignore

    def _remaining_deployable_cash(self) -> float:
        allowed = self._max_allowed_invested() - self._invested_value()
        return max(0.0, min(self._cash(), allowed))

    def _buy_accumulated_reserve(self, signal_name: str) -> None:
        if self._already_bought_this_month():
            return

        cash_to_use = min(
            self.accumulated_reserve,
            self._remaining_deployable_cash(),
            self._cash(),
        )

        if cash_to_use < self.p.min_order_cash:
            return

        price = float(self.minute_data.close[0])
        if price <= 0:
            return

        size = cash_to_use / price

        if size <= 0:
            return

        current_date = self.minute_data.datetime.date(0)
        current_time = self.minute_data.datetime.datetime(0)

        self.buy(size=size)
        self.buy_count += 1
        self.last_buy_month = self._current_year_month()
        self.accumulated_reserve -= cash_to_use

        if self.buy_count <= 20:
            print(
                f"[TacticalVolumeDCA] Buy #{self.buy_count} | "
                f"{signal_name} | {current_time} | "
                f"size={size:.6f} | price=${price:.2f} | "
                f"invested=${cash_to_use:.2f} | "
                f"remaining_reserve=${self.accumulated_reserve:.2f} | "
                f"exposure={self._current_exposure_pct():.1%} | "
                f"cash=${self._cash():.2f}"
            )

    def next_open(self) -> None:
        """
        Called at bar open for execution logic.
        Uses next_open() to align with intraday execution pattern.
        """
        # Process monthly contribution
        self._process_monthly_contribution()

        # Track portfolio metrics
        dt = self.minute_data.datetime.date(0)
        close = float(self.minute_data.close[0])
        cash = float(self._cash())
        value = float(self._portfolio_value())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)
        self.reserve_history.append(self.accumulated_reserve)
        self.exposure_pct.append(self._current_exposure_pct())

        # Wait for indicators to warm up
        min_bars_minute = self.p.volume_sma_period
        min_bars_daily = self.p.daily_bb_period if self.has_daily_data else 0

        if len(self.minute_data) < min_bars_minute:
            return

        if self.has_daily_data and len(self.daily_data) < min_bars_daily:
            return

        # Check if already bought this month
        if self._already_bought_this_month():
            return

        # Check if have sufficient reserve
        if self.accumulated_reserve < self.p.min_order_cash:
            return

        # Check if have remaining deployable cash
        if self._remaining_deployable_cash() < self.p.min_order_cash:
            return

        # Get current values
        minute_price = float(self.minute_data.close[0])
        minute_volume = float(self.minute_data.volume[0])
        avg_volume = float(self.minute_volume_sma[0])

        # Check 1: Volume spike on minute data
        volume_spike = minute_volume > avg_volume * self.p.volume_threshold

        if not volume_spike:
            return

        # Check 2: Daily correction (price below middle Bollinger Band)
        if not self.has_daily_data:
            return  # Need daily data for correction detection

        daily_price = float(self.daily_close[0])
        daily_mid_bb = float(self.daily_bbands.mid[0])

        correction_active = daily_price < daily_mid_bb

        if not correction_active:
            return

        # Both conditions met: Deploy accumulated reserve
        volume_ratio = minute_volume / avg_volume
        correction_pct = (daily_mid_bb - daily_price) / daily_mid_bb * 100

        signal_name = (
            f"Volume Spike ({volume_ratio:.1f}x) + "
            f"BB Mid Dip ({correction_pct:.1f}% below)"
        )

        self._buy_accumulated_reserve(signal_name)

    def notify_order(self, order: bt.Order) -> None:
        """Handle order notifications and track executions for analytics."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            # Track order execution for analytics
            self._track_order_execution(order)

            # Record trade entry immediately
            if order.isbuy():
                self._record_trade_entry(order)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"ORDER FAILED | Status: {order.getstatusname()}")

    def stop(self) -> None:
        # Finalize any OPEN trades as ACCUMULATED
        self._finalize_open_trades()

        final_value = self.broker.getvalue()
        final_cash = self.broker.getcash()
        position = self.getposition()

        print(
            f"[TacticalVolumeDCA] stop() called - "
            f"total_buys={self.buy_count}, "
            f"final_value=${final_value:,.2f}, "
            f"final_cash=${final_cash:,.2f}, "
            f"remaining_reserve=${self.accumulated_reserve:,.2f}, "
            f"position_size={position.size:.6f}"
        )

        # Plot portfolio breakdown
        if len(self.dates) > 0:
            plt.figure(figsize=(10, 6))
            plt.plot(self.dates, self.cash, label="Cash")
            plt.plot(self.dates, self.position_value, label="Position Value")
            plt.plot(self.dates, self.total_value, label="Total Portfolio Value")
            plt.plot(self.dates, self.reserve_history, label="Accumulated Reserve")

            plt.xlabel("Date")
            plt.ylabel("Value ($)")
            plt.title("TacticalVolumeDCA - Portfolio Breakdown")
            plt.legend()
            plt.grid(True)
            plt.tight_layout()

            if self.p.show_plot:
                plt.show()
            else:
                plt.close()
