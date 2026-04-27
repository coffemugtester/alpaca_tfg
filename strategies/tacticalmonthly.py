from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class TacticalMonthlyRedistributed(bt.Strategy):
    """
    Tactical monthly strategy with DCA-style capital restriction.

    Capital is available from day 1, but deployment is constrained monthly.

    Rule:
    - Divide remaining deployable capital across remaining months.
    - Maximum one buy per month.
    - If no signal occurs in a month, capital is not invested.
    - Next month, the monthly budget is recalculated over remaining months.

    Signals:
    - Bull market filter: Close > SMA200 and SMA50 > SMA200
    - Dip: RSI < threshold
    - Momentum: MACD crosses above signal
    - Breakout: Close > Upper Bollinger Band

    No selling logic.
    """

    params = dict(
        sma_fast=50,
        sma_slow=200,
        rsi_period=14,
        dip_rsi=40,
        bb_period=20,
        bb_devfactor=2.0,
        max_exposure=0.995,
        min_order_cash=250.0,
        show_plot=True,
    )

    def __init__(self):
        self.close = self.datas[0].close

        self.sma_fast = bt.ind.SMA(self.close, period=self.p.sma_fast)
        self.sma_slow = bt.ind.SMA(self.close, period=self.p.sma_slow)

        self.rsi = bt.ind.RSI(self.close, period=self.p.rsi_period)

        self.macd = bt.ind.MACD(self.close)
        self.macd_cross = bt.ind.CrossOver(self.macd.macd, self.macd.signal)

        self.bbands = bt.ind.BollingerBands(
            self.close,
            period=self.p.bb_period,
            devfactor=self.p.bb_devfactor,
        )

        self.initial_cash = None
        self.start_year_month = None
        self.end_year_month = None
        self.total_months = None

        self.last_buy_month = None
        self.buy_count = 0

        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

    def start(self):
        self.initial_cash = self.broker.getcash()

        start_date = self.datas[0].datetime.date(0)
        end_date = self.datas[0].datetime.date(-1)

        self.start_year_month = (start_date.year, start_date.month)
        self.end_year_month = (end_date.year, end_date.month)

        self.total_months = (
            self._months_between(
                self.start_year_month,
                self.end_year_month,
            )
            + 1
        )

        print(f"[TacticalMonthlyRedistributed] Initial cash: ${self.initial_cash:,.2f}")
        print(f"[TacticalMonthlyRedistributed] Total months: {self.total_months}")

    def _months_between(self, start_ym, end_ym) -> int:
        start_year, start_month = start_ym
        end_year, end_month = end_ym
        return (end_year - start_year) * 12 + (end_month - start_month)

    def _current_year_month(self):
        dt = self.datas[0].datetime.date(0)
        return (dt.year, dt.month)

    def _elapsed_months(self) -> int:
        return self._months_between(
            self.start_year_month,
            self._current_year_month(),
        )

    def _remaining_months(self) -> int:
        return max(1, self.total_months - self._elapsed_months())

    def _portfolio_value(self):
        return self.broker.getvalue()

    def _cash(self):
        return self.broker.getcash()

    def _invested_value(self):
        return self._portfolio_value() - self._cash()

    def _max_allowed_invested(self):
        return self.initial_cash * self.p.max_exposure

    def _remaining_deployable_cash(self):
        allowed = self._max_allowed_invested() - self._invested_value()
        return max(0.0, min(self._cash(), allowed))

    def _monthly_budget(self):
        return self._remaining_deployable_cash() / self._remaining_months()

    def _already_bought_this_month(self) -> bool:
        return self.last_buy_month == self._current_year_month()

    def _buy_monthly_budget(self, signal_name: str):
        if self._already_bought_this_month():
            return

        cash_to_use = self._monthly_budget()

        if cash_to_use < self.p.min_order_cash:
            return

        price = float(self.close[0])
        size = int(cash_to_use / price)

        if size <= 0:
            return

        order_cash = size * price

        if order_cash < self.p.min_order_cash:
            return

        current_month = self._current_year_month()
        current_date = self.datas[0].datetime.date(0)

        self.buy(size=size)
        self.buy_count += 1
        self.last_buy_month = current_month

        if self.buy_count <= 20:
            print(
                f"[TacticalMonthlyRedistributed] Buy #{self.buy_count} | "
                f"{signal_name} | {current_date} | "
                f"size={size} | price=${price:.2f} | "
                f"monthly_budget=${cash_to_use:.2f} | "
                f"remaining_months={self._remaining_months()} | "
                f"cash=${self._cash():.2f}"
            )

    def next(self):
        dt = self.datas[0].datetime.date(0)
        close = float(self.close[0])
        cash = float(self._cash())
        value = float(self._portfolio_value())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        min_bars = max(
            self.p.sma_slow,
            self.p.rsi_period,
            self.p.bb_period,
        )

        if len(self) < min_bars:
            return

        if self._remaining_deployable_cash() < self.p.min_order_cash:
            return

        if self._already_bought_this_month():
            return

        price = self.close[0]

        bullish_trend = price > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]

        if not bullish_trend:
            return

        # Signal 1: RSI dip
        if self.rsi[0] < self.p.dip_rsi:
            self._buy_monthly_budget("RSI Dip")
            return

        # Signal 2: MACD momentum
        momentum_resume = self.macd_cross[0] > 0 and price > self.sma_fast[0]

        if momentum_resume:
            self._buy_monthly_budget("MACD Momentum")
            return

        # Signal 3: Bollinger breakout
        bollinger_breakout = price > self.bbands.top[0]

        if bollinger_breakout:
            self._buy_monthly_budget("Bollinger Breakout")

    def stop(self) -> None:
        final_value = self.broker.getvalue()
        final_cash = self.broker.getcash()
        position = self.getposition()

        print(
            f"[TacticalMonthlyRedistributed] stop() called - "
            f"total_buys={self.buy_count}, "
            f"final_value=${final_value:,.2f}, "
            f"final_cash=${final_cash:,.2f}, "
            f"position_size={position.size}"
        )

        plt.figure(figsize=(10, 6))
        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title("TacticalMonthlyRedistributed - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        if self.p.show_plot:
            plt.show()
        else:
            plt.close()
