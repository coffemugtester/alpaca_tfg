from __future__ import annotations

from datetime import datetime
from typing import Type

import backtrader as bt

from data.alpaca_data import fetch_daily_bars
from .data_adapter import df_to_bt_feed


def run_backtest(
    symbol: str,
    start: datetime,
    end: datetime,
    strategy: Type[bt.Strategy],
    cash: float,
    commission: float,
) -> float:
    """
    Orchestrate a full backtest run: fetch data, prepare it, wire it into Backtrader,
    and return the final portfolio value.
    """

    df = fetch_daily_bars(symbol=symbol, start=start, end=end)

    print(df.head())
    print("\nRows:", len(df))
    print("Columns:", list(df.columns))
    print("Index type:", type(df.index))

    data_feed = df_to_bt_feed(df)

    print(data_feed.p.dataname.head())
    print("tz:", data_feed.p.dataname.index.tz)

    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed, name=symbol)

    cerebro.addstrategy(strategy)

    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)

    print("Bars loaded:", len(data_feed.p.dataname))
    print("Starting value:", cerebro.broker.getvalue())

    cerebro.run()

    final_value = float(cerebro.broker.getvalue())
    print("Final value:", final_value)

    return final_value

