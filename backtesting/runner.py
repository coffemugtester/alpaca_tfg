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
    slippage: float,
    strategy_params: dict | None = None,
) -> float:
    """
    Orchestrate a full backtest run: fetch data, prepare it, wire it into Backtrader,
    and return the final portfolio value.

    Args:
        strategy_params: Optional dict of parameters to pass to the strategy
        slippage: Slippage percentage (e.g., 0.0005 for 0.05%)
    """

    df = fetch_daily_bars(symbol=symbol, start=start, end=end)

    print(df.head())
    print("\nRows:", len(df))
    print("Columns:", list(df.columns))
    print("Index type:", type(df.index))

    data_feed = df_to_bt_feed(df)

    print(data_feed.p.dataname.head())
    print("tz:", data_feed.p.dataname.index.tz)

    cerebro = bt.Cerebro(cheat_on_open=True)  # Enable next_open() callbacks
    cerebro.adddata(data_feed, name=symbol)

    if strategy_params:
        cerebro.addstrategy(strategy, **strategy_params)
    else:
        cerebro.addstrategy(strategy)

    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)
    cerebro.broker.set_slippage_perc(slippage)

    print("Bars loaded:", len(data_feed.p.dataname))
    print("Starting value:", cerebro.broker.getvalue())

    cerebro.run()

    final_value = float(cerebro.broker.getvalue())
    print("Final value:", final_value)

    return final_value

