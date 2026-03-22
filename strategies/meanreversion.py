from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class MeanReversionStrategy(bt.Strategy):
    """
    Mean reversion strategy (buy-the-dip within an uptrend):
    - Trend filter: short SMA > long SMA and price > long SMA
    - Pullback detection: RSI weakens and/or price touches lower Bollinger Band
    - Rebound confirmation: MACD crosses above signal after pullback
    - Max one entry per month
    - Monthly capital budget with carry-over bucket
    - NEVER sells - holds positions forever

    This strategy tests:
    "Can I improve long-term accumulation by buying pullbacks inside an uptrend,
    instead of buying breakouts?"
    """

    params = dict(
        sma_fast=50,
        sma_slow=200,
        rsi_period=14,
        rsi_pullback=45,  # pullback threshold
        bb_period=20,
        bb_devfactor=2.0,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        max_deploy=0.995,  # invest up to 99.5% of initial cash
        allow_fractional=True,
        printlog=True,
    )

    def __init__(self) -> None:
        self.order = None
        self.entry_price = None
        self.entry_date = None
        self.entry_size = None
        self.initial_cash = None

        # Series for portfolio metrics
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

        # Trade tracking
        self.trades = []
        self.entries = []

        # Monthly budgeting state
        self.current_month_key = None
        self.last_entry_month_key = None
        self.deployable_total = None
        self.monthly_slice = None
        self.budget_bucket = 0.0
        self.total_budget_released = 0.0
        self.total_invested = 0.0

        # Pullback / rebound state
        self.pullback_armed = False
        self.pullback_arm_date = None

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

        self.macd_cross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

        self.bbands = bt.indicators.BollingerBands(
            self.data.close,
            period=self.p.bb_period,
            devfactor=self.p.bb_devfactor,
        )

    def log(self, txt: str) -> None:
        if self.p.printlog:
            dt = self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()} | {txt}")

    def _count_backtest_months(self) -> int:
        """
        Count distinct calendar months present in the loaded data feed.
        This is used to split the deployable capital into monthly slices.
        """
        seen = set()
        for i in range(len(self.data)):
            dt = bt.num2date(self.data.datetime.array[i]).date()
            seen.add((dt.year, dt.month))
        return max(1, len(seen))

    def _release_monthly_budget_if_needed(self, dt) -> None:
        """
        Release exactly one monthly slice the first time we see a new month.
        """
        month_key = (dt.year, dt.month)

        if self.current_month_key != month_key:
            self.current_month_key = month_key

            remaining_budget_to_release = max(
                0.0, self.deployable_total - self.total_budget_released
            )

            release = min(self.monthly_slice, remaining_budget_to_release)
            self.budget_bucket += release
            self.total_budget_released += release

            if release > 0:
                self.log(
                    f"NEW MONTH | Released budget: ${release:,.2f} | "
                    f"Bucket available: ${self.budget_bucket:,.2f}"
                )

    def next(self) -> None:
        dt = self.datas[0].datetime.date(0)
        close = float(self.data.close[0])

        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        # Capture initial cash and initialize monthly budget model
        if self.initial_cash is None:
            self.initial_cash = cash
            months = self._count_backtest_months()
            self.deployable_total = self.initial_cash * self.p.max_deploy
            self.monthly_slice = self.deployable_total / months

        # collect metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # avoid placing new orders if one is pending
        if self.order:
            return

        # release monthly budget once per new calendar month
        self._release_monthly_budget_if_needed(dt)

        # =========================
        # TREND FILTER
        # =========================
        trend_ok = close > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]

        # =========================
        # PULLBACK DETECTION
        # =========================
        rsi_pullback = self.rsi[0] < self.p.rsi_pullback
        lower_band_touch = close <= self.bbands.bot[0]

        pullback_now = trend_ok and (rsi_pullback or lower_band_touch)

        if pullback_now and not self.pullback_armed:
            self.pullback_armed = True
            self.pullback_arm_date = dt
            self.log(
                f"PULLBACK ARMED | Close: {close:.2f} | "
                f"RSI: {self.rsi[0]:.2f} | "
                f"BB Bot: {self.bbands.bot[0]:.2f}"
            )

        # If trend is lost, disarm setup
        if self.pullback_armed and not trend_ok:
            self.pullback_armed = False
            self.pullback_arm_date = None
            self.log("PULLBACK DISARMED | Trend lost")

        # =========================
        # REBOUND CONFIRMATION
        # =========================
        rebound_now = self.macd_cross[0] > 0

        month_key = (dt.year, dt.month)
        already_entered_this_month = self.last_entry_month_key == month_key

        signal_ok = (
            trend_ok
            and self.pullback_armed
            and rebound_now
            and not already_entered_this_month
        )

        if signal_ok:
            remaining_deployable = max(0.0, self.deployable_total - self.total_invested)
            invest = min(self.budget_bucket, remaining_deployable, cash)

            if invest > 0:
                size = invest / close

                if not self.p.allow_fractional:
                    size = int(size)
                    invest = size * close

                if size > 0 and invest > 0:
                    self.log(
                        f"BUY SIGNAL | Budget used: ${invest:,.2f} | "
                        f"Bucket before buy: ${self.budget_bucket:,.2f} | "
                        f"Close: {close:.2f} | "
                        f"SMA{self.p.sma_fast}: {self.sma_fast[0]:.2f} | "
                        f"SMA{self.p.sma_slow}: {self.sma_slow[0]:.2f} | "
                        f"RSI: {self.rsi[0]:.2f} | "
                        f"MACD Cross: {self.macd_cross[0]:.0f} | "
                        f"Armed since: {self.pullback_arm_date}"
                    )
                    self.order = self.buy(size=size)

        # =========================
        # EXITS DISABLED
        # =========================
        # No sells on purpose. The strategy only times entries.

    def notify_order(self, order: bt.Order) -> None:
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                entry_price = float(order.executed.price)
                entry_date = self.datas[0].datetime.date(0)
                entry_size = float(order.executed.size)
                invested = entry_price * entry_size

                self.entries.append(
                    {
                        "date": entry_date,
                        "price": entry_price,
                        "size": entry_size,
                        "invested": invested,
                    }
                )

                self.entry_price = entry_price
                self.entry_date = entry_date
                self.entry_size = entry_size

                # update monthly budgeting state
                self.total_invested += invested
                self.budget_bucket = max(0.0, self.budget_bucket - invested)
                self.last_entry_month_key = (entry_date.year, entry_date.month)

                # reset pullback state after successful entry
                self.pullback_armed = False
                self.pullback_arm_date = None

        self.order = None

    def stop(self) -> None:
        """Print entry summary and plot portfolio breakdown at end of backtest."""
        print("\n" + "=" * 80)
        print("MEAN REVERSION STRATEGY - ENTRY TIMING SUMMARY")
        print("(Buy pullbacks in uptrend, one entry max per month, no exits)")
        print("=" * 80)

        initial_cash = self.initial_cash if self.initial_cash is not None else 0.0
        final_cash = float(self.broker.getcash())
        final_value = float(self.broker.getvalue())

        deployable_total = (
            self.deployable_total if self.deployable_total is not None else 0.0
        )
        monthly_slice = self.monthly_slice if self.monthly_slice is not None else 0.0

        print(f"\nCAPITAL BUDGET MODEL:")
        print(f"  Initial Cash:        ${initial_cash:>13,.2f}")
        print(f"  Max Deploy ({self.p.max_deploy:.3f}): ${deployable_total:>13,.2f}")
        print(f"  Monthly Slice:       ${monthly_slice:>13,.2f}")
        print(f"  Released Budget:     ${self.total_budget_released:>13,.2f}")
        print(f"  Remaining Bucket:    ${self.budget_bucket:>13,.2f}")

        if not self.entries:
            print(f"\nRESULT:")
            print(f"  Final Cash:          ${final_cash:>13,.2f}")
            print(f"  Total Invested:      ${0:>13,.2f}")
            print(f"  Deployed:            {0:>12.1f}%")
            print(f"  Remaining in Cash:   {100:>12.1f}%")
            print(
                "\nNo entries made (likely no pullback+rebound signals after warm-up)."
            )
        else:
            num_entries = len(self.entries)
            total_invested = sum(e["invested"] for e in self.entries)
            pct_deployed = (
                (total_invested / initial_cash * 100) if initial_cash > 0 else 0
            )
            pct_remaining = (final_cash / initial_cash * 100) if initial_cash > 0 else 0

            print(f"\nCASH DEPLOYMENT:")
            print(f"  Final Cash:          ${final_cash:>13,.2f}")
            print(f"  Total Invested:      ${total_invested:>13,.2f}")
            print(f"  Deployed:            {pct_deployed:>12.1f}%")
            print(f"  Remaining in Cash:   {pct_remaining:>12.1f}%")

            avg_invested = total_invested / num_entries if num_entries > 0 else 0
            avg_price = (
                sum(e["price"] for e in self.entries) / num_entries
                if num_entries > 0
                else 0
            )

            current_price = float(self.datas[0].close[0])
            total_shares = sum(e["size"] for e in self.entries)
            current_value = total_shares * current_price
            total_gain = current_value - total_invested
            total_gain_pct = (
                (total_gain / total_invested * 100) if total_invested > 0 else 0
            )

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
            print(
                f"  Cash:     ${final_cash:>13,.2f}  ({final_cash / final_value * 100:>5.1f}%)"
            )
            print(
                f"  Position: ${current_value:>13,.2f}  ({current_value / final_value * 100:>5.1f}%)"
            )
            print(f"  Total:    ${final_value:>13,.2f}")

            print(f"\nENTRY HISTORY")
            print(f"{'-' * 80}")
            print(
                f"{'#':<4} {'Date':<12} {'Price':>10} {'Shares':>12} {'Invested':>14}"
            )
            print(f"{'-' * 80}")

            for i, entry in enumerate(self.entries, 1):
                print(
                    f"{i:<4} {str(entry['date']):<12} "
                    f"${entry['price']:>9.2f} {entry['size']:>12.4f} "
                    f"${entry['invested']:>13.2f}"
                )

            print(f"{'-' * 80}")
            print(
                f"{'TOTAL':<17} {'':<10} {total_shares:>12.4f} ${total_invested:>13.2f}"
            )

        print("=" * 80 + "\n")

        plt.figure(figsize=(10, 6))
        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        num_entries_text = (
            f"{len(self.entries)} entries" if self.entries else "no entries"
        )
        plt.title(
            f"MeanReversion (Monthly Budgeted Entries) - Portfolio Breakdown ({num_entries_text})"
        )
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.show()
        # plt.savefig("reports/meanreversion_portfolio.png")
        # plt.close()
