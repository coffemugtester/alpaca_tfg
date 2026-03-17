from __future__ import annotations

import backtrader as bt


class BuyFirstSellInStop(bt.Strategy):
    def __init__(self) -> None:
        self.did_buy = False

    def next(self) -> None:
        dt = self.datas[0].datetime.date(0)
        close = float(self.datas[0].close[0])

        cash = float(self.broker.getcash())
        value = float(self.broker.getvalue())
        pos = self.getposition()

        pos_size = float(pos.size)
        pos_price = float(pos.price)
        pos_value = pos_size * close

        print(
            f\"{dt} close={close:.2f} | "
            f\"cash={cash:.2f} | "
            f\"price={pos_price} | "
            f\"pos_size={pos_size} | "
            f\"pos_value={pos_value:.2f} | "
            f\"total={value:.2f}\"
        )

        if not pos:
            self.buy(size=1)

    def stop(self) -> None:
        if self.position:
            close = float(self.datas[0].close[0])
            self.sell(size=self.position.size)
            print(f" SELL (end) @ {close:.2f}")

