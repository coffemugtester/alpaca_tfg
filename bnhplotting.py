import matplotlib.pyplot as plt
import backtrader as bt


class BuyAndHold(bt.Strategy):
    params = dict(
        allow_fractional=True,
        cash_buffer=0.995,  # invierte el 99.5% para evitar rechazo por redondeo/gap
    )

    def __init__(self):
        self.dates = []
        self.cash = []
        self.position_value = []
        self.total_value = []

        self.entered = False
        self.order = None

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

        # Buy once at the beginning using almost all available cash
        if not self.entered and self.order is None:
            invest = cash * self.p.cash_buffer
            size = invest / close

            if not self.p.allow_fractional:
                size = int(size)

            if size > 0:
                self.order = self.buy(size=size)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            print(
                f"BUY EXECUTED | Price: {order.executed.price:.2f} | "
                f"Size: {order.executed.size:.6f} | "
                f"Cost: {order.executed.value:.2f} | "
                f"Comm: {order.executed.comm:.2f}"
            )
            self.entered = True

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"ORDER FAILED | Status: {order.getstatusname()}")

        self.order = None

    def stop(self):
        plt.figure(figsize=(10, 6))

        plt.plot(self.dates, self.cash, label="Cash")
        plt.plot(self.dates, self.position_value, label="Position Value")
        plt.plot(self.dates, self.total_value, label="Total Portfolio Value")

        plt.xlabel("Date")
        plt.ylabel("Value ($)")
        plt.title("Buy & Hold - Portfolio Breakdown")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.show()
