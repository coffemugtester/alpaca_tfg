from __future__ import annotations

from datetime import date

import backtrader as bt
import matplotlib.pyplot as plt


class TacticalMonthlyRedistributed(bt.Strategy):
    """
    Tactical DCA with accumulated monthly savings.

    Logic:
    - Simulates a DCA investor with a fixed monthly contribution.
    - Each month, one monthly contribution becomes available.
    - If there is no technical signal, the contribution remains in cash.
    - When a valid signal appears, the accumulated cash reserve is invested.
    - Maximum one buy per calendar month.
    - No selling logic.
    """

    params = dict(
        sma_fast=50,
        sma_slow=200,
        rsi_period=14,
        dip_rsi=40,
        bb_period=20,
        bb_devfactor=2.0,
        max_exposure=0.995,
        min_order_cash=1.0,
        show_plot=True,
    )

    def __init__(self) -> None:
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

        self.initial_cash: float | None = None
        self.start_year_month: tuple[int, int] | None = None
        self.end_year_month: tuple[int, int] | None = None
        self.total_months: int | None = None
        self.monthly_contribution: float | None = None

        self.current_month: tuple[int, int] | None = None
        self.accumulated_reserve: float = 0.0
        self.last_buy_month: tuple[int, int] | None = None
        self.buy_count: int = 0

        self.dates: list[date] = []
        self.cash: list[float] = []
        self.position_value: list[float] = []
        self.total_value: list[float] = []
        self.reserve_history: list[float] = []

    def start(self) -> None:
        self.initial_cash = self.broker.getcash()

        data_dates = [
            bt.num2date(self.datas[0].datetime.array[i]).date()
            for i in range(len(self.datas[0].datetime.array))
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

        print(f"[TacticalAccumulatedDCA] Initial cash: ${self.initial_cash:,.2f}")
        print(f"[TacticalAccumulatedDCA] Start month: {self.start_year_month}")
        print(f"[TacticalAccumulatedDCA] End month: {self.end_year_month}")
        print(f"[TacticalAccumulatedDCA] Total months: {self.total_months}")
        print(
            f"[TacticalAccumulatedDCA] Monthly contribution: "
            f"${self.monthly_contribution:,.2f}"
        )

    def _months_between(
        self, start_ym: tuple[int, int], end_ym: tuple[int, int]
    ) -> int:
        start_year, start_month = start_ym
        end_year, end_month = end_ym
        return (end_year - start_year) * 12 + (end_month - start_month)

    def _current_year_month(self) -> tuple[int, int]:
        dt = self.datas[0].datetime.date(0)
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

        price = float(self.close[0])
        if price <= 0:
            return

        size = cash_to_use / price

        if size <= 0:
            return

        current_date = self.datas[0].datetime.date(0)

        self.buy(size=size)
        self.buy_count += 1
        self.last_buy_month = self._current_year_month()
        self.accumulated_reserve -= cash_to_use

        if self.buy_count <= 20:
            print(
                f"[TacticalAccumulatedDCA] Buy #{self.buy_count} | "
                f"{signal_name} | {current_date} | "
                f"size={size:.6f} | price=${price:.2f} | "
                f"invested=${cash_to_use:.2f} | "
                f"remaining_reserve=${self.accumulated_reserve:.2f} | "
                f"cash=${self._cash():.2f}"
            )

    def next(self) -> None:
        self._process_monthly_contribution()

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
        self.reserve_history.append(self.accumulated_reserve)

        min_bars = max(self.p.sma_slow, self.p.rsi_period, self.p.bb_period)

        if len(self) < min_bars:
            return

        if self._remaining_deployable_cash() < self.p.min_order_cash:
            return

        if self.accumulated_reserve < self.p.min_order_cash:
            return

        if self._already_bought_this_month():
            return

        price = self.close[0]

        bullish_trend = price > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]

        if not bullish_trend:
            return

        if self.rsi[0] < self.p.dip_rsi:
            self._buy_accumulated_reserve("RSI Dip")
            return

        momentum_resume = self.macd_cross[0] > 0 and price > self.sma_fast[0]

        if momentum_resume:
            self._buy_accumulated_reserve("MACD Momentum")
            return

        bollinger_breakout = price > self.bbands.top[0]

        if bollinger_breakout:
            self._buy_accumulated_reserve("Bollinger Breakout")

    def stop(self) -> None:
        final_value = self.broker.getvalue()
        final_cash = self.broker.getcash()
        position = self.getposition()

        print(
            f"[TacticalAccumulatedDCA] stop() called - "
            f"total_buys={self.buy_count}, "
            f"final_value=${final_value:,.2f}, "
            f"final_cash=${final_cash:,.2f}, "
            f"remaining_reserve=${self.accumulated_reserve:,.2f}, "
            f"position_size={position.size:.6f}"
        )

        plt.figure(figsize=(10, 6))
        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")
        plt.plot(self.dates, self.reserve_history, label="Accumulated Reserve")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title("TacticalAccumulatedDCA - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        if self.p.show_plot:
            plt.show()
        else:
            plt.close()
