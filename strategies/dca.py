from __future__ import annotations

import backtrader as bt
import matplotlib.pyplot as plt


class DollarCostAveraging(bt.Strategy):
    """
    Dollar Cost Averaging strategy (without external contributions):
    - Starts with initial cash (set via broker, e.g., $10,000)
    - Spreads this cash evenly across all months in the backtest timeframe
    - Invests the calculated monthly amount from available cash each month
    - Holds positions; never sells
    - Records cash, position value, and total value per bar, plots at end

    Note: monthly_invest is automatically calculated as initial_cash / num_months
    by the caller (main.py or ValidationPipeline). The default value is only
    used if the strategy is run manually without this parameter.
    """

    params = dict(
        monthly_invest=100.0,  # default if not specified; typically overridden
        allow_fractional=True,  # True for fractional ETFs (if broker/data supports)
    )

    def __init__(self) -> None:
        # series para métricas
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

        # para detectar cambio de mes (evitar comprar múltiples veces en el mismo mes)
        self._last_year = None
        self._last_month = None

    def next(self) -> None:
        # Barra actual (ya cerrada)
        dt = self.datas[0].datetime.date(0)
        close = float(self.datas[0].close[0])

        # Estado del broker / portfolio
        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        # collect metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # --- Lógica DCA mensual ---
        current_period = (dt.year, dt.month)
        last_period = (self._last_year, self._last_month)

        # Solo actuamos el primer día hábil que aparece de cada nuevo mes
        if current_period != last_period:
            self._last_year, self._last_month = dt.year, dt.month

            invest = float(self.p.monthly_invest)

            # si no hay cash suficiente, invierte lo que quede (o si prefieres: "skip")
            invest = min(invest, cash)

            # si ya no queda cash, no hacemos nada
            if invest <= 0:
                return

            # calcular size a comprar con ese importe
            size = invest / close

            if not self.p.allow_fractional:
                # acciones típicas: unidades enteras
                size = int(size)

            if size <= 0:
                return

            # market order (por defecto ejecuta en la barra siguiente)
            self.buy(size=size)

    def stop(self) -> None:
        plt.figure(figsize=(10, 6))

        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        monthly_invest_display = f"${self.p.monthly_invest:.2f}"
        plt.title(f"DCA ({monthly_invest_display}/month) - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.show()
        # plt.savefig("reports/dca_portfolio.png")
        # plt.close()

