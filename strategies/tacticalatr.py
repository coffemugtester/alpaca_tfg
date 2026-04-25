from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class TacticalTrendDipReserve(bt.Strategy):
    """
    Tactical Trend + Dip Reserve Strategy

    Goal:
    Avoid deploying all capital too early.
    Preserve reserve capital for meaningful corrections.

    Logic:
    - Normal bull-market signals can deploy only up to a base exposure cap.
    - Deeper drawdowns unlock additional capital.
    - Recovery confirmation avoids buying too aggressively during falling markets.
    - No selling logic.
    """

    params = dict(
        sma_fast=50,
        sma_slow=200,
        rsi_period=14,
        dip_rsi=40,
        deep_rsi=30,
        bb_period=20,
        bb_devfactor=2.0,
        # Capital architecture
        max_exposure=0.995,
        base_exposure_cap=0.50,  # normal signals can only deploy up to 50%
        # Drawdown ladder from recent peak
        dd_5_cap=0.60,
        dd_10_cap=0.75,
        dd_15_cap=0.90,
        dd_20_cap=0.995,
        lookback_peak=252,  # approx 1 trading year
        # Normal signal tranches
        tranche_dip=0.15,
        tranche_momentum=0.10,
        tranche_breakout=0.07,
        # Correction reserve tranches
        tranche_correction=0.25,
        tranche_deep_correction=0.40,
        min_order_cash=250.0,
        cooldown_days=14,
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

        self.recent_peak = bt.ind.Highest(
            self.close,
            period=self.p.lookback_peak,
        )

        self.initial_cash = None
        self.last_buy_date = None
        self.buy_count = 0

        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []
        self.exposure_pct = []

    def start(self):
        self.initial_cash = self.broker.getcash()
        print(f"[TacticalTrendDipReserve] Initial cash: ${self.initial_cash:,.2f}")
        print(
            f"[TacticalTrendDipReserve] Base exposure cap: {self.p.base_exposure_cap:.0%}"
        )
        print(f"[TacticalTrendDipReserve] Cooldown: {self.p.cooldown_days} days")

    def _portfolio_value(self):
        return self.broker.getvalue()

    def _cash(self):
        return self.broker.getcash()

    def _invested_value(self):
        return self._portfolio_value() - self._cash()

    def _current_exposure_pct(self):
        value = self._portfolio_value()
        if value <= 0:
            return 0.0
        return self._invested_value() / value

    def _cap_cash_allowed(self, exposure_cap: float):
        target_invested = self._portfolio_value() * min(
            exposure_cap, self.p.max_exposure
        )
        remaining_allowed = target_invested - self._invested_value()
        return max(0.0, min(self._cash(), remaining_allowed))

    def _cooldown_active(self) -> bool:
        if self.last_buy_date is None:
            return False

        current_date = self.datas[0].datetime.date(0)
        days_since_last_buy = (current_date - self.last_buy_date).days

        return days_since_last_buy < self.p.cooldown_days

    def _buy_cash_amount(self, cash_to_use: float, signal_name: str):
        if cash_to_use < self.p.min_order_cash:
            return

        if self._cooldown_active():
            return

        price = float(self.close[0])
        if price <= 0:
            return

        size = int(cash_to_use / price)

        if size <= 0:
            return

        order_cash = size * price

        if order_cash < self.p.min_order_cash:
            return

        current_date = self.datas[0].datetime.date(0)

        self.buy(size=size)
        self.buy_count += 1
        self.last_buy_date = current_date

        if self.buy_count <= 20:
            print(
                f"[TacticalTrendDipReserve] Buy #{self.buy_count} | "
                f"{signal_name} | {current_date} | "
                f"size={size} | price=${price:.2f} | "
                f"order_cash=${order_cash:.2f} | "
                f"exposure={self._current_exposure_pct():.1%}"
            )

    def _drawdown_from_peak(self):
        peak = float(self.recent_peak[0])
        price = float(self.close[0])

        if peak <= 0:
            return 0.0

        return (peak - price) / peak

    def _drawdown_exposure_cap(self, drawdown: float):
        if drawdown >= 0.20:
            return self.p.dd_20_cap
        if drawdown >= 0.15:
            return self.p.dd_15_cap
        if drawdown >= 0.10:
            return self.p.dd_10_cap
        if drawdown >= 0.05:
            return self.p.dd_5_cap

        return self.p.base_exposure_cap

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
        self.exposure_pct.append(self._current_exposure_pct())

        min_bars = max(
            self.p.sma_slow,
            self.p.rsi_period,
            self.p.bb_period,
            self.p.lookback_peak,
        )

        if len(self) < min_bars:
            return

        price = self.close[0]
        drawdown = self._drawdown_from_peak()
        allowed_cap = self._drawdown_exposure_cap(drawdown)

        bullish_trend = price > self.sma_slow[0] and self.sma_fast[0] > self.sma_slow[0]

        recovery_confirmation = self.macd_cross[0] > 0 or self.rsi[0] > self.rsi[-1]

        bollinger_breakout = price > self.bbands.top[0]

        # =====================================================
        # 1. RESERVE DEPLOYMENT DURING CORRECTIONS
        # =====================================================
        # This can happen even if the strict bull trend is damaged,
        # but requires some sign of recovery.
        if drawdown >= 0.10 and recovery_confirmation:
            cash_available = self._cap_cash_allowed(allowed_cap)

            if cash_available >= self.p.min_order_cash:
                tranche = (
                    self.p.tranche_deep_correction
                    if drawdown >= 0.15 or self.rsi[0] < self.p.deep_rsi
                    else self.p.tranche_correction
                )

                amount = cash_available * tranche
                self._buy_cash_amount(
                    amount,
                    signal_name=f"Correction Reserve DD={drawdown:.1%}",
                )
                return

        # =====================================================
        # 2. NORMAL BULL-MARKET DEPLOYMENT
        # =====================================================
        # Normal signals are capped at base exposure.
        if not bullish_trend:
            return

        normal_cash_available = self._cap_cash_allowed(self.p.base_exposure_cap)

        if normal_cash_available < self.p.min_order_cash:
            return

        # Signal 1: RSI dip inside bull trend
        if self.rsi[0] < self.p.dip_rsi:
            amount = normal_cash_available * self.p.tranche_dip
            self._buy_cash_amount(amount, signal_name="RSI Dip Base")
            return

        # Signal 2: renewed momentum
        momentum_resume = self.macd_cross[0] > 0 and price > self.sma_fast[0]

        if momentum_resume:
            amount = normal_cash_available * self.p.tranche_momentum
            self._buy_cash_amount(amount, signal_name="MACD Momentum Base")
            return

        # Signal 3: Bollinger breakout strength
        if bollinger_breakout:
            amount = normal_cash_available * self.p.tranche_breakout
            self._buy_cash_amount(amount, signal_name="Bollinger Breakout Base")

    def stop(self) -> None:
        final_value = self.broker.getvalue()
        final_cash = self.broker.getcash()
        position = self.getposition()

        print(
            f"[TacticalTrendDipReserve] stop() called - "
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
        plt.title("TacticalTrendDipReserve - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        if self.p.show_plot:
            plt.show()
        else:
            plt.close()
