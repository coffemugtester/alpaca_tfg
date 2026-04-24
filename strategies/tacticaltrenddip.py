from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class TacticalTrendDipStrategy(bt.Strategy):
    """
    Tactical Trend + Dip Deployment

    Capital already available from day 1.
    Objective:
    Deploy capital progressively using technical signals instead of monthly limits.

    Philosophy:
    - Avoid buying during weak macro trend.
    - Buy pullbacks inside uptrend.
    - Add on renewed momentum.
    - Add on breakout strength.

    No selling logic included (entry optimization only),
    making it comparable to Buy & Hold style accumulation.
    """

    params = dict(
        sma_fast=50,
        sma_slow=200,
        rsi_period=14,
        breakout_period=60,
        dip_rsi=40,
        tranche_dip=0.25,  # 25% remaining cash
        tranche_momentum=0.15,  # 15%
        tranche_breakout=0.10,  # 10%
        min_order_cash=250.0,  # avoid tiny orders
        max_exposure=0.995,  # deploy max 99.5%
        show_plot=True,  # whether to display matplotlib chart at end
    )

    def __init__(self):
        self.close = self.datas[0].close

        self.sma_fast = bt.ind.SMA(self.close, period=self.p.sma_fast)
        self.sma_slow = bt.ind.SMA(self.close, period=self.p.sma_slow)

        self.rsi = bt.ind.RSI(self.close, period=self.p.rsi_period)

        self.macd = bt.ind.MACD(self.close)
        self.macd_cross = bt.ind.CrossOver(self.macd.macd, self.macd.signal)

        self.highest = bt.ind.Highest(self.close(-1), period=self.p.breakout_period)

        self.initial_cash = None

        # Metrics tracking
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

    def start(self):
        self.initial_cash = self.broker.getcash()
        self.buy_count = 0
        print(f"[TacticalTrendDip] start() called - initial_cash captured: ${self.initial_cash:,.2f}")

    def _portfolio_value(self):
        return self.broker.getvalue()

    def _invested_value(self):
        return self._portfolio_value() - self.broker.getcash()

    def _max_allowed_invested(self):
        return self.initial_cash * self.p.max_exposure

    def _remaining_deployable_cash(self):
        allowed = self._max_allowed_invested() - self._invested_value()
        return max(0.0, min(self.broker.getcash(), allowed))

    def _buy_cash_amount(self, cash_to_use: float):
        if cash_to_use < self.p.min_order_cash:
            return

        size = int(cash_to_use / self.close[0])
        if size > 0:
            self.buy(size=size)
            self.buy_count += 1
            if self.buy_count <= 5:  # Log first 5 buys only
                dt = self.datas[0].datetime.date(0)
                print(f"[TacticalTrendDip] Buy #{self.buy_count} on {dt}: size={size}, price=${self.close[0]:.2f}, invest=${cash_to_use:.2f}")

    def next(self):
        # Track metrics
        dt = self.datas[0].datetime.date(0)
        close = float(self.close[0])
        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        if len(self) < self.p.sma_slow:
            return

        price = self.close[0]
        cash_available = self._remaining_deployable_cash()

        if cash_available < self.p.min_order_cash:
            return

        # ==============================
        # MAIN TREND FILTER
        # ==============================
        bullish_trend = price > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]

        if not bullish_trend:
            return

        # ==============================
        # SIGNAL PRIORITY 1:
        # Buy dip inside uptrend
        # ==============================
        if self.rsi[0] < self.p.dip_rsi:
            amount = cash_available * self.p.tranche_dip
            self._buy_cash_amount(amount)
            return

        # ==============================
        # SIGNAL PRIORITY 2:
        # Renewed momentum
        # ==============================
        momentum_resume = self.macd_cross[0] > 0 and price > self.sma_fast[0]

        if momentum_resume:
            amount = cash_available * self.p.tranche_momentum
            self._buy_cash_amount(amount)
            return

        # ==============================
        # SIGNAL PRIORITY 3:
        # Breakout strength
        # ==============================
        breakout = price > self.highest[0]

        if breakout:
            amount = cash_available * self.p.tranche_breakout
            self._buy_cash_amount(amount)

    def stop(self) -> None:
        final_value = self.broker.getvalue()
        final_cash = self.broker.getcash()
        position = self.getposition()
        print(f"[TacticalTrendDip] stop() called - total_buys={self.buy_count}, final_value=${final_value:,.2f}, final_cash=${final_cash:,.2f}, position_size={position.size}")

        plt.figure(figsize=(10, 6))
        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title("TacticalTrendDip - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        if self.p.show_plot:
            plt.show()
        else:
            plt.close()
