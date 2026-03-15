import backtrader as bt


class BuyFirstSellInStop(bt.Strategy):
    def __init__(self):
        self.did_buy = False

    def next(self):
        dt = self.datas[0].datetime.date(0)
        close = self.datas[0].close[0]

        cash = self.broker.getcash()
        value = self.broker.getvalue()
        pos = self.getposition()

        pos_size = pos.size
        pos_price = pos.price
        pos_value = pos_size * close

        print(
            f"{dt} close={close:.2f} | "
            f"cash={cash:.2f} | "
            f"price={pos_price} | "
            f"pos_size={pos_size} | "
            f"pos_value={pos_value:.2f} | "
            f"total={value:.2f}"
        )

        if not pos:
            self.buy(size=1)

    def stop(self):
        if self.position:
            close = self.datas[0].close[0]
            self.sell(size=self.position.size)
            print(f" SELL (end) @ {close:.2f}")
