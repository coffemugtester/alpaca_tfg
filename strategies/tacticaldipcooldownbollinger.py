from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class TacticalTrendDipCooldownBollinger(bt.Strategy):
    """
    Tactical Trend + Dip Deployment with 4-Week Cooldown

    Breakout signal now uses Bollinger Bands:
    - Buy breakout strength when Close > Upper Bollinger Band.
    """

    params = dict(
        sma_fast=50,
        sma_slow=200,
        rsi_period=14,
        bb_period=20,
        bb_devfactor=2.0,
        dip_rsi=40,
        tranche_dip=0.25,
        tranche_momentum=0.15,
        tranche_breakout=0.10,
        min_order_cash=250.0,
        max_exposure=0.995,
        cooldown_days=28,
        show_plot=True,
    )

    def __init__(self):
        self.close = self.datas[0].close

        self.sma_fast = bt.ind.SMA(self.close, period=self.p.sma_fast)
        self.sma_slow = bt.ind.SMA(self.close, period=self.p.sma_slow)

        self.rsi = bt.ind.RSI(self.close, period=self.p.rsi_period)

        self.macd = bt.ind.MACD(self.close)
        self.macd_cross = bt.ind.CrossOver(self.macd.macd, self.macd.signal)

        # Bollinger Bands instead of Highest(60)
        self.bbands = bt.ind.BollingerBands(
            self.close,
            period=self.p.bb_period,
            devfactor=self.p.bb_devfactor,
        )

        self.initial_cash = None
        self.last_buy_date = None

        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

    def start(self):
        self.initial_cash = self.broker.getcash()
        self.buy_count = 0
        print(
            f"[TacticalDipCooldown] start() called - initial_cash captured: ${self.initial_cash:,.2f}"
        )
        print(f"[TacticalDipCooldown] Cooldown period: {self.p.cooldown_days} days")
        print(
            f"[TacticalDipCooldown] Bollinger Bands: period={self.p.bb_period}, devfactor={self.p.bb_devfactor}"
        )

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

        current_date = self.datas[0].datetime.date(0)

        if self.last_buy_date is not None:
            days_since_last_buy = (current_date - self.last_buy_date).days
            if days_since_last_buy < self.p.cooldown_days:
                if self.buy_count <= 5:
                    print(
                        f"[TacticalDipCooldown] Cooldown active on {current_date}: "
                        f"{days_since_last_buy} days since last buy "
                        f"(need {self.p.cooldown_days})"
                    )
                return

        size = int(cash_to_use / self.close[0])

        if size > 0:
            days_since = (
                "N/A (first buy)"
                if self.last_buy_date is None
                else (current_date - self.last_buy_date).days
            )

            self.buy(size=size)
            self.buy_count += 1

            if self.buy_count <= 5:
                print(
                    f"[TacticalDipCooldown] Buy #{self.buy_count} on {current_date}: "
                    f"size={size}, price=${self.close[0]:.2f}, "
                    f"invest=${cash_to_use:.2f}, days_since_last={days_since}"
                )

            self.last_buy_date = current_date

    def next(self):
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

        min_bars = max(self.p.sma_slow, self.p.bb_period)
        if len(self) < min_bars:
            return

        price = self.close[0]
        cash_available = self._remaining_deployable_cash()

        if cash_available < self.p.min_order_cash:
            return

        bullish_trend = price > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]

        if not bullish_trend:
            return

        # Signal 1: dip inside uptrend
        if self.rsi[0] < self.p.dip_rsi:
            amount = cash_available * self.p.tranche_dip
            self._buy_cash_amount(amount)
            return

        # Signal 2: renewed momentum
        momentum_resume = self.macd_cross[0] > 0 and price > self.sma_fast[0]

        if momentum_resume:
            amount = cash_available * self.p.tranche_momentum
            self._buy_cash_amount(amount)
            return

        # Signal 3: Bollinger breakout strength
        bollinger_breakout = price > self.bbands.top[0]

        if bollinger_breakout:
            amount = cash_available * self.p.tranche_breakout
            self._buy_cash_amount(amount)

    def stop(self) -> None:
        final_value = self.broker.getvalue()
        final_cash = self.broker.getcash()
        position = self.getposition()

        print(
            f"[TacticalDipCooldown] stop() called - total_buys={self.buy_count}, "
            f"final_value=${final_value:,.2f}, final_cash=${final_cash:,.2f}, "
            f"position_size={position.size}"
        )

        plt.figure(figsize=(10, 6))
        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title("TacticalDipCooldown + Bollinger Breakout - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        if self.p.show_plot:
            plt.show()
        else:
            plt.close()
