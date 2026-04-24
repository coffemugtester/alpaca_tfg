from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class DipBuyerStrategy(bt.Strategy):
    """
    DipBuyer strategy - Iteration 9: Hybrid DCA + Strategic (configurable split).

    Philosophy: Split monthly capital to get best of both approaches.
    Default: 70% DCA / 30% Strategic (configurable via dca_weight param)

    **DCA Bucket (default 70%):**
    - Deploys automatically every month (guaranteed exposure)
    - Eliminates cash drag on majority of capital
    - ~120 entries over 10 years

    **Strategic Bucket (default 30%):**
    - Accumulates monthly
    - Deploys on drawdowns using aggressive sizing
    - ~20-40 selective entries

    Strategic Entry Modes (either triggers entry):
    1. Bull pullback: price > SMA200 AND price < SMA20
    2. Major correction: drawdown from 252-day high >= 3%
    3. Fallback: if accumulated > 3 months strategic budget

    Strategic Position Sizing (aggressive):
    - 15%+ drawdown: 100% of accumulated strategic
    - 10-15% drawdown: 100%
    - 5-10% drawdown: 75%
    - 3-5% drawdown: 60%
    - Fallback mode: 50%
    - Hard floor: NEVER deploy less than 50%

    Monthly Limit: Max one strategic entry per month (DCA always fires)

    Realistic Constraint:
    - NEVER exceeds accumulated strategic budget

    Key Difference from Pure DCA:
    - Pure DCA: 120 entries, average price, full exposure, high cash drag in dips
    - Hybrid v9: 120 DCA + 20-40 strategic, lower avg price on strategic half
    """

    params = dict(
        monthly_invest=100.0,  # default if not specified; typically overridden
        allow_fractional=True,  # True for fractional ETFs (if broker/data supports)
        dca_weight=0.70,  # DCA bucket weight (0.70 = 70% DCA, 30% strategic)
    )

    def __init__(self) -> None:
        # series for metrics
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

        # detect month change for budget accumulation
        self._last_year = None
        self._last_month = None

        # Track last entry month for monthly limit
        self._last_entry_year = None
        self._last_entry_month = None

        # Iteration 6: Trend + Dip + Drawdown detection
        self.sma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=20)
        self.sma200 = bt.indicators.SimpleMovingAverage(self.data.close, period=200)

        # Track 252-day (1-year) high for drawdown calculation
        self.highest_252 = bt.indicators.Highest(self.data.close, period=252)

        # Iteration 9: Hybrid 50/50 structure
        # Strategic bucket accumulates, DCA bucket deploys immediately
        self.accumulated_strategic = 0.0

        # Deployment tracking metrics
        self._dca_entry_count = 0
        self._strategic_entry_count = 0
        self._total_strategic_deploy_pct = 0.0
        self._total_accumulated_at_entry = 0.0
        self._max_accumulated_strategic = 0.0

    def prenext(self) -> None:
        """
        Called during indicator warmup period (before all indicators ready).
        Only DCA buys - strategic waits for indicators.
        """
        dt = self.datas[0].datetime.date(0)
        close = float(self.datas[0].close[0])

        # Broker state
        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        # Collect metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # Monthly budget handling
        current_period = (dt.year, dt.month)
        last_period = (self._last_year, self._last_month)

        if current_period != last_period:
            self._last_year, self._last_month = dt.year, dt.month

            monthly = float(self.p.monthly_invest)
            dca_weight = float(self.p.dca_weight)
            strategic_weight = 1.0 - dca_weight

            dca_amount = monthly * dca_weight
            strategic_amount = monthly * strategic_weight

            # DCA bucket: buy immediately (no indicators needed)
            dca_size = dca_amount / close
            if not self.p.allow_fractional:
                dca_size = int(dca_size)
                dca_amount = dca_size * close

            if dca_size > 0 and dca_amount > 0:
                self.buy(size=dca_size)
                self._dca_entry_count += 1

            # Strategic bucket: accumulate for later deployment
            self.accumulated_strategic += strategic_amount

        # Track max accumulated strategic
        if self.accumulated_strategic > self._max_accumulated_strategic:
            self._max_accumulated_strategic = self.accumulated_strategic

    def next(self) -> None:
        # Current bar (already closed)
        dt = self.datas[0].datetime.date(0)
        close = float(self.datas[0].close[0])

        # Broker / portfolio state
        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        # collect metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # --- Iteration 9: Hybrid 50/50 DCA + Strategic ---
        current_period = (dt.year, dt.month)
        last_period = (self._last_year, self._last_month)

        # On first trading day of each new month: split budget by dca_weight
        if current_period != last_period:
            self._last_year, self._last_month = dt.year, dt.month

            monthly = float(self.p.monthly_invest)
            dca_weight = float(self.p.dca_weight)
            strategic_weight = 1.0 - dca_weight

            dca_amount = monthly * dca_weight
            strategic_amount = monthly * strategic_weight

            # DCA bucket: buy immediately every month
            dca_size = dca_amount / close
            if not self.p.allow_fractional:
                dca_size = int(dca_size)
                dca_amount = dca_size * close

            if dca_size > 0 and dca_amount > 0:
                self.buy(size=dca_size)
                self._dca_entry_count += 1

            # Strategic bucket: accumulate for opportunistic deployment
            self.accumulated_strategic += strategic_amount

        # Track max accumulated strategic budget
        if self.accumulated_strategic > self._max_accumulated_strategic:
            self._max_accumulated_strategic = self.accumulated_strategic

        # Calculate drawdown from 252-day high
        drawdown_pct = (self.highest_252[0] - close) / self.highest_252[0]

        # MODE 1: Bull pullback (price > SMA200 AND price < SMA20)
        bull_pullback = close > self.sma200[0] and close < self.sma20[0]

        # MODE 2: Major correction (drawdown >= 3%, even if below SMA200)
        major_correction = drawdown_pct >= 0.03

        # MONTHLY LIMIT: Haven't entered this month yet
        current_entry_period = (dt.year, dt.month)
        last_entry_period = (self._last_entry_year, self._last_entry_month)
        can_enter_this_month = current_entry_period != last_entry_period

        # Entry signal: (bull pullback OR major correction) AND monthly limit
        entry_signal = (bull_pullback or major_correction) and can_enter_this_month

        # MODE 3: Fallback to prevent cash drag on strategic bucket
        strategic_monthly = self.p.monthly_invest * (1.0 - self.p.dca_weight)
        fallback_signal = (
            not entry_signal
            and can_enter_this_month
            and self.accumulated_strategic > 3 * strategic_monthly
        )

        # STRATEGIC DEPLOYMENT (use accumulated_strategic only)
        if (entry_signal or fallback_signal) and self.accumulated_strategic > 0:
            # Aggressive drawdown-based position sizing
            if fallback_signal:
                # Fallback mode: deploy 50% to prevent cash drag
                deploy_pct = 0.50
            elif drawdown_pct >= 0.15:
                # Deep correction (15%+): deploy everything
                deploy_pct = 1.0
            elif drawdown_pct >= 0.10:
                # Moderate correction (10-15%): deploy 100%
                deploy_pct = 1.0
            elif drawdown_pct >= 0.05:
                # Small dip (5-10%): deploy 75%
                deploy_pct = 0.75
            elif drawdown_pct >= 0.03:
                # Minor pullback (3-5%): deploy 60%
                deploy_pct = 0.60
            else:
                # Less than 3% drawdown in bull pullback mode: deploy 60%
                deploy_pct = 0.60

            # Hard floor: never deploy less than 50%
            deploy_pct = max(deploy_pct, 0.50)

            # Calculate strategic investment (NEVER exceeds accumulated strategic budget)
            invest = self.accumulated_strategic * deploy_pct
            invest = min(invest, cash)  # Also cap by available cash

            if invest <= 0:
                return

            # calculate size to buy with that amount
            size = invest / close

            if not self.p.allow_fractional:
                # typical stocks: whole units
                size = int(size)
                invest = size * close  # recalculate invest for whole shares

            if size > 0 and invest > 0:
                # market order (executes on next bar by default)
                self.buy(size=size)

                # Update strategic entry tracking
                self._last_entry_year = dt.year
                self._last_entry_month = dt.month

                # Update strategic deployment metrics
                self._strategic_entry_count += 1
                self._total_strategic_deploy_pct += deploy_pct
                self._total_accumulated_at_entry += self.accumulated_strategic

                # Deduct what we spent from accumulated strategic budget
                self.accumulated_strategic -= invest

    def stop(self) -> None:
        # Print hybrid deployment statistics
        print("\n" + "=" * 60)
        print("HYBRID DIPBUYER DEPLOYMENT METRICS")
        print("=" * 60)

        total_months = 120  # 10-year backtest
        total_entries = self._dca_entry_count + self._strategic_entry_count

        avg_strategic_deploy_pct = (
            (self._total_strategic_deploy_pct / self._strategic_entry_count)
            if self._strategic_entry_count > 0
            else 0.0
        )
        avg_accumulated_at_strategic_entry = (
            (self._total_accumulated_at_entry / self._strategic_entry_count)
            if self._strategic_entry_count > 0
            else 0.0
        )

        # Calculate cash idle ratio (average cash / average total value)
        avg_cash = sum(self.cash) / len(self.cash) if len(self.cash) > 0 else 0.0
        avg_total_value = (
            sum(self.total_value) / len(self.total_value)
            if len(self.total_value) > 0
            else 0.0
        )
        cash_idle_ratio = (avg_cash / avg_total_value) if avg_total_value > 0 else 0.0

        print(f"DCA entries:               {self._dca_entry_count} (auto every month)")
        print(f"Strategic entries:         {self._strategic_entry_count}")
        print(f"Total entries:             {total_entries}")
        print(f"Avg strategic deploy %:    {avg_strategic_deploy_pct*100:.1f}%")
        print(f"Avg accumulated strategic: ${avg_accumulated_at_strategic_entry:.2f}")
        print(f"Max accumulated strategic: ${self._max_accumulated_strategic:.2f}")
        print(f"Cash idle ratio:           {cash_idle_ratio*100:.1f}%")
        print("=" * 60 + "\n")

        # Plot
        plt.figure(figsize=(10, 6))

        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        dca_pct = self.p.dca_weight * 100
        strategic_pct = (1.0 - self.p.dca_weight) * 100
        plt.title(
            f"DipBuyer Iteration 9 (Hybrid: {dca_pct:.0f}% DCA + {strategic_pct:.0f}% Strategic)"
        )
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.show()
