import matplotlib.pyplot as plt
import backtrader as bt


class BuyAndHold(bt.Strategy):
    """
    Buy & Hold con inversión limitada:
    - El broker puede tener más cash (p.ej. 10.000$ en paper).
    - La estrategia invierte solo una vez un importe fijo (p.ej. 1200$).
    - Mantiene la posición hasta el final.
    - Registra cash, valor de la posición y valor total.
    """

    params = dict(
        entry_cash=1200.0,  # cuánto invertir en la entrada
        allow_fractional=True,  # False si quieres unidades enteras
    )

    def __init__(self):
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

        self.entered = False  # asegura una sola compra

    def next(self):
        dt = self.datas[0].datetime.date(0)
        close = float(self.datas[0].close[0])

        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()
        pos_value = float(pos.size) * close

        # collect metrics
        self.dates.append(dt)
        self.cash.append(cash)
        self.position_value.append(pos_value)
        self.total_value.append(value)

        # Comprar una sola vez usando SOLO entry_cash (o menos si no hay suficiente cash)
        if not self.entered:
            invest = min(
                float(self.p.entry_cash), cash
            )  # por si el broker tuviese menos
            size = invest / close

            if not self.p.allow_fractional:
                size = int(size)

            if size > 0:
                self.buy(size=size)
                self.entered = True

    def stop(self):
        plt.figure(figsize=(10, 6))

        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title("Buy & Hold (Entry = 1200$) - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.show()
        # plt.savefig("reports/buy_and_hold_portfolio.png")
        # pltclose()
