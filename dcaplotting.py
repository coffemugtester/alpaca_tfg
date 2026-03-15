import matplotlib.pyplot as plt
import backtrader as bt


class DollarCostAveraging(bt.Strategy):
    """
    DCA (sin aportaciones externas):
    - Partes de un cash inicial (p.ej., 10.000$ en el broker).
    - Cada mes inviertes 100$ del cash disponible (si lo hay).
    - Mantienes la posición; no vendes.
    - Registra cash, valor de posición y valor total en cada barra y lo grafica al final.
    """

    params = dict(
        monthly_invest=100.0,  # cuánto invertir cada mes desde el cash existente
        allow_fractional=True,  # True para ETFs fraccionales (si tu broker/data lo soporta)
    )

    def __init__(self):
        # series para métricas
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

        # para detectar cambio de mes (evitar comprar múltiples veces en el mismo mes)
        self._last_year = None
        self._last_month = None

    def next(self):
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

    def stop(self):
        plt.figure(figsize=(10, 6))

        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title("DCA (100$/month from initial cash) - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.show()
        # plt.savefig("reports/dca_portfolio.png")
        # plt.close()
