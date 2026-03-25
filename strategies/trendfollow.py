from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class TrendFollowingStrategy(bt.Strategy):
    """
    Entry-timing strategy with dynamic monthly capital redistribution:
    - Trend filter: short SMA > long SMA and price > long SMA
    - Momentum confirmation: MACD > signal
    - Strength filter: RSI within a healthy range
    - Entry trigger: breakout above upper Bollinger Band

    Capital deployment logic:
    - Max one entry per month
    - Total deployable capital is capped at 99.5% of initial cash
    - Remaining deployable capital is dynamically redistributed across remaining months
    - No exits: positions are held permanently
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

        # Dynamic monthly allocation state
        self.current_month_key = None
        self.last_entry_month_key = None
        self.deployable_total = None
        self.total_months = None
        self.elapsed_months = 0
        self.current_month_budget = 0.0
        self.total_invested = 0.0

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

        self.macd_cross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

    def log(self, txt: str) -> None:
        if self.p.printlog:
            dt = self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()} | {txt}")

    def _count_backtest_months(self) -> int:
        """
        Count distinct calendar months present in the loaded data feed.
        Used to dynamically redistribute remaining capital.
        """
        seen = set()
        for i in range(len(self.data)):
            dt = bt.num2date(self.data.datetime.array[i]).date()
            seen.add((dt.year, dt.month))
        return max(1, len(seen))

    def _recalculate_monthly_budget_if_needed(self, dt) -> None:
        """
        On the first bar of each new month, recalculate the budget for the month
        as remaining deployable capital divided by remaining months.
        """
        month_key = (dt.year, dt.month)

        if self.current_month_key != month_key:
            self.current_month_key = month_key
            self.elapsed_months += 1

            remaining_deployable = max(0.0, self.deployable_total - self.total_invested)
            remaining_months = max(1, self.total_months - self.elapsed_months + 1)

            self.current_month_budget = remaining_deployable / remaining_months

            self.log(
                f"NEW MONTH | Budget recalculated: ${self.current_month_budget:,.2f} | "
                f"Remaining deployable: ${remaining_deployable:,.2f} | "
                f"Remaining months: {remaining_months}"
            )

    def next(self) -> None:
        dt = self.datas[0].datetime.date(0)
        close = float(self.data.close[0])

        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        # Capture initial cash and initialize dynamic budget model
        if self.initial_cash is None:
            self.initial_cash = cash
            self.total_months = self._count_backtest_months()
            self.deployable_total = self.initial_cash * self.p.max_deploy

        # collect metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # avoid placing new orders if one is pending
        if self.order:
            return

        # recalculate budget once per new calendar month
        self._recalculate_monthly_budget_if_needed(dt)

        # =========================
        # ENTRY CONDITIONS
        # =========================
        trend_ok = close > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]
        momentum_ok = self.macd.macd[0] > self.macd.signal[0]
        rsi_ok = self.p.rsi_min <= self.rsi[0] <= self.p.rsi_max
        breakout_ok = close > self.bbands.top[0]

        signal_ok = trend_ok and momentum_ok and rsi_ok and breakout_ok
        month_key = (dt.year, dt.month)
        already_entered_this_month = self.last_entry_month_key == month_key

        if signal_ok and not already_entered_this_month:
            remaining_deployable = max(0.0, self.deployable_total - self.total_invested)
            invest = min(self.current_month_budget, remaining_deployable, cash)

            if invest > 0:
                size = invest / close

                if not self.p.allow_fractional:
                    size = int(size)
                    invest = size * close

                if size > 0 and invest > 0:
                    self.log(
                        f"BUY SIGNAL | Budget used: ${invest:,.2f} | "
                        f"Monthly budget: ${self.current_month_budget:,.2f} | "
                        f"Close: {close:.2f} | "
                        f"SMA{self.p.sma_fast}: {self.sma_fast[0]:.2f} | "
                        f"SMA{self.p.sma_slow}: {self.sma_slow[0]:.2f} | "
                        f"RSI: {self.rsi[0]:.2f} | "
                        f"MACD: {self.macd.macd[0]:.4f} > Signal: {self.macd.signal[0]:.4f}"
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

                # update deployment state
                self.total_invested += invested
                self.last_entry_month_key = (entry_date.year, entry_date.month)

        self.order = None

    def stop(self) -> None:
        """Print entry summary and plot portfolio breakdown at end of backtest."""
        print("\n" + "=" * 80)
        print("TRENDFOLLOWING STRATEGY - ENTRY TIMING SUMMARY")
        print("(One entry max per month, dynamic monthly redistribution, no exits)")
        print("=" * 80)

        initial_cash = self.initial_cash if self.initial_cash is not None else 0.0
        final_cash = float(self.broker.getcash())
        final_value = float(self.broker.getvalue())

        deployable_total = (
            self.deployable_total if self.deployable_total is not None else 0.0
        )
        total_months = self.total_months if self.total_months is not None else 0
        remaining_deployable = max(0.0, deployable_total - self.total_invested)

        print(f"\nCAPITAL BUDGET MODEL:")
        print(f"  Initial Cash:        ${initial_cash:>13,.2f}")
        print(f"  Max Deploy ({self.p.max_deploy:.3f}): ${deployable_total:>13,.2f}")
        print(f"  Total Months:        {total_months:>13}")
        print(f"  Months Elapsed:      {self.elapsed_months:>13}")
        print(f"  Last Month Budget:   ${self.current_month_budget:>13,.2f}")
        print(f"  Remaining Deployable:${remaining_deployable:>13,.2f}")

        if not self.entries:
            print(f"\nRESULT:")
            print(f"  Final Cash:          ${final_cash:>13,.2f}")
            print(f"  Total Invested:      ${0:>13,.2f}")
            print(f"  Deployed:            {0:>12.1f}%")
            print(f"  Remaining in Cash:   {100:>12.1f}%")
            print("\nNo entries made (likely no signals after warm-up).")
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
            f"TrendFollowing (Dynamic Monthly Redistribution) - Portfolio Breakdown ({num_entries_text})"
        )
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.show()
