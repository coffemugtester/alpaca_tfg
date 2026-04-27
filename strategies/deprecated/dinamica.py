from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class DinamicaStrategy(bt.Strategy):
    """
    Dinámica - Iteration 12: Hybrid DCA + Value Averaging Recovery Buyer.

    Structure:
    - DCA bucket: invested automatically every month.
    - Strategic bucket: accumulated in a side fund.
    - Strategic deployment follows a Value Averaging logic.
    - Strategic entry occurs when:
        1. Price is below SMA200 (weak long-term regime)
        2. Price has recovered above SMA20 (short-term rebound)
        3. Fallback activates after excess strategic cash accumulation

    Purpose:
    Test whether entering on confirmed rebounds after weakness
    performs better than buying direct drawdowns.
    """

    params = dict(
        monthly_invest=100.0,
        allow_fractional=True,
        dca_weight=0.70,
        va_expected_monthly_return=0.0,
        fallback_after_months=3,
        show_plot=True,  # whether to display matplotlib chart at end
    )

    def __init__(self) -> None:
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

        self._last_year = None
        self._last_month = None

        self._last_strategic_entry_year = None
        self._last_strategic_entry_month = None

        self.sma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=20)
        self.sma200 = bt.indicators.SimpleMovingAverage(self.data.close, period=200)

        # Strategic side fund
        self.accumulated_strategic_cash = 0.0
        self.strategic_shares = 0.0
        self.strategic_target_value = 0.0

        # Metrics
        self._dca_entry_count = 0
        self._strategic_entry_count = 0
        self._months_elapsed = 0
        self._max_accumulated_strategic = 0.0
        self._total_va_gap_at_entry = 0.0

    def prenext(self) -> None:
        self._process_bar(indicators_ready=False)

    def next(self) -> None:
        self._process_bar(indicators_ready=True)

    def _process_bar(self, indicators_ready: bool) -> None:
        dt = self.datas[0].datetime.date(0)
        close = float(self.datas[0].close[0])

        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        # Metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # =====================
        # NEW MONTH CONTRIBUTION
        # =====================
        current_period = (dt.year, dt.month)
        last_period = (self._last_year, self._last_month)

        new_month = current_period != last_period

        if new_month:
            self._last_year, self._last_month = dt.year, dt.month
            self._months_elapsed += 1

            monthly = float(self.p.monthly_invest)
            dca_weight = float(self.p.dca_weight)
            strategic_weight = 1.0 - dca_weight

            dca_amount = monthly * dca_weight
            strategic_amount = monthly * strategic_weight

            # Automatic DCA part
            self._buy_amount(dca_amount, close)
            self._dca_entry_count += 1

            # Strategic reserve
            self.accumulated_strategic_cash += strategic_amount

            # Value Averaging target grows monthly
            self.strategic_target_value = (
                self.strategic_target_value
                * (1.0 + float(self.p.va_expected_monthly_return))
                + strategic_amount
            )

        self._max_accumulated_strategic = max(
            self._max_accumulated_strategic,
            self.accumulated_strategic_cash,
        )

        if not indicators_ready:
            return

        # =====================
        # VALUE AVERAGING GAP
        # =====================
        strategic_market_value = self.strategic_shares * close
        va_gap = self.strategic_target_value - strategic_market_value

        if va_gap <= 0:
            return

        # =====================
        # ENTRY SIGNAL
        # =====================
        # Weak long-term regime, but short-term rebound
        recovery_after_downtrend = close < self.sma200[0] and close > self.sma20[0]

        # Monthly limit
        current_entry_period = (dt.year, dt.month)
        last_entry_period = (
            self._last_strategic_entry_year,
            self._last_strategic_entry_month,
        )
        can_enter_this_month = current_entry_period != last_entry_period

        # Fallback if reserve too large
        strategic_monthly = self.p.monthly_invest * (1.0 - self.p.dca_weight)

        fallback_signal = (
            self.accumulated_strategic_cash
            >= self.p.fallback_after_months * strategic_monthly
        )

        entry_signal = can_enter_this_month and (
            recovery_after_downtrend or fallback_signal
        )

        if not entry_signal:
            return

        # =====================
        # POSITION SIZING
        # =====================
        invest = min(
            va_gap,
            self.accumulated_strategic_cash,
            cash,
        )

        if invest <= 0:
            return

        size = invest / close

        if not self.p.allow_fractional:
            size = int(size)
            invest = size * close

        if size <= 0 or invest <= 0:
            return

        self.buy(size=size)

        self.strategic_shares += size
        self.accumulated_strategic_cash -= invest

        self._last_strategic_entry_year = dt.year
        self._last_strategic_entry_month = dt.month

        self._strategic_entry_count += 1
        self._total_va_gap_at_entry += va_gap

    def _buy_amount(self, amount: float, close: float) -> None:
        cash = float(self.broker.getcash())
        invest = min(amount, cash)

        if invest <= 0:
            return

        size = invest / close

        if not self.p.allow_fractional:
            size = int(size)
            invest = size * close

        if size > 0 and invest > 0:
            self.buy(size=size)

    def stop(self) -> None:
        avg_va_gap = (
            self._total_va_gap_at_entry / self._strategic_entry_count
            if self._strategic_entry_count > 0
            else 0.0
        )

        avg_cash = sum(self.cash) / len(self.cash) if self.cash else 0.0
        avg_total_value = (
            sum(self.total_value) / len(self.total_value) if self.total_value else 0.0
        )
        cash_idle_ratio = avg_cash / avg_total_value if avg_total_value > 0 else 0.0

        print("\n" + "=" * 60)
        print("HYBRID DCA + VALUE AVERAGING DINÁMICA METRICS")
        print("=" * 60)
        print(f"DCA entries:                 {self._dca_entry_count}")
        print(f"Strategic VA entries:        {self._strategic_entry_count}")
        print(f"Months elapsed:              {self._months_elapsed}")
        print(f"Strategic target value:      ${self.strategic_target_value:.2f}")
        print(f"Strategic shares:            {self.strategic_shares:.4f}")
        print(f"Remaining strategic cash:    ${self.accumulated_strategic_cash:.2f}")
        print(f"Max strategic cash:          ${self._max_accumulated_strategic:.2f}")
        print(f"Avg VA gap at entry:         ${avg_va_gap:.2f}")
        print(f"Cash idle ratio:             {cash_idle_ratio*100:.1f}%")
        print("=" * 60 + "\n")

        plt.figure(figsize=(10, 6))
        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        dca_pct = self.p.dca_weight * 100
        strategic_pct = (1.0 - self.p.dca_weight) * 100

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title(
            f"Dinámica Iteration 12 "
            f"({dca_pct:.0f}% DCA + {strategic_pct:.0f}% Recovery VA)"
        )
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        if self.p.show_plot:
            plt.show()
        else:
            plt.close()
