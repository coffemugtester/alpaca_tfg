from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class TrendFollowingStrategy(bt.Strategy):
    """
    Algorithmic strategy based on:
    - Trend filter: short SMA > long SMA and price > long SMA
    - Momentum confirmation: MACD > signal
    - Strength filter: RSI within a healthy range
    - Entry trigger: breakout above upper Bollinger Band
    - Risk management:
        * percentage stop-loss
        * percentage take-profit
        * exit on trend loss
        * exit on bearish MACD
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
        stop_loss=0.05,  # 5%
        take_profit=0.15,  # 15%
        cash_buffer=0.995,
        allow_fractional=True,
        printlog=True,
    )

    def __init__(self) -> None:
        self.order = None
        self.entry_price = None

        # Series for portfolio metrics
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

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

        # collect metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # avoid placing new orders if one is pending
        if self.order:
            return

        # =========================
        # ENTRY
        # =========================
        if not self.position:
            trend_ok = close > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]

            momentum_ok = self.macd.macd[0] > self.macd.signal[0]
            rsi_ok = self.p.rsi_min <= self.rsi[0] <= self.p.rsi_max

            # Breakout condition: close above upper Bollinger Band
            breakout_ok = close > self.bbands.top[0]

            if trend_ok and momentum_ok and rsi_ok and breakout_ok:
                invest = cash * self.p.cash_buffer
                size = invest / close

                if not self.p.allow_fractional:
                    size = int(size)

                if size > 0:
                    self.log(
                        f"BUY SIGNAL | Close: {close:.2f} | "
                        f"SMA{self.p.sma_fast}: {self.sma_fast[0]:.2f} | "
                        f"SMA{self.p.sma_slow}: {self.sma_slow[0]:.2f} | "
                        f"RSI: {self.rsi[0]:.2f} | "
                        f"MACD: {self.macd.macd[0]:.4f} > Signal: {self.macd.signal[0]:.4f}"
                    )
                    self.order = self.buy(size=size)

        # =========================
        # EXIT
        # =========================
        else:
            if self.entry_price is None:
                return

            stop_price = self.entry_price * (1.0 - self.p.stop_loss)
            take_price = self.entry_price * (1.0 + self.p.take_profit)

            stop_hit = close <= stop_price
            take_hit = close >= take_price

            trend_lost = (
                close < self.sma_fast[0]
                or close < self.sma_slow[0]
                or self.sma_fast[0] < self.sma_slow[0]
            )

            macd_bearish = self.macd.macd[0] < self.macd.signal[0]

            if stop_hit:
                self.log(f"SELL SIGNAL | STOP LOSS | Close: {close:.2f}")
                self.order = self.sell(size=self.position.size)

            elif take_hit:
                self.log(f"SELL SIGNAL | TAKE PROFIT | Close: {close:.2f}")
                self.order = self.sell(size=self.position.size)

            elif trend_lost:
                self.log(f"SELL SIGNAL | TREND LOST | Close: {close:.2f}")
                self.order = self.sell(size=self.position.size)

            elif macd_bearish:
                self.log(f"SELL SIGNAL | MACD BEARISH | Close: {close:.2f}")
                self.order = self.sell(size=self.position.size)

    def notify_order(self, order: bt.Order) -> None:
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.entry_price = float(order.executed.price)
            elif order.issell():
                self.entry_price = None

        self.order = None

    def stop(self) -> None:
        """Plot portfolio breakdown at end of backtest."""
        plt.figure(figsize=(10, 6))

        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title("TrendFollowing Strategy - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.show()
        # plt.savefig("reports/trendfollowing_portfolio.png")
        # plt.close()
