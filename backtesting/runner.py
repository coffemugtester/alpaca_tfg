from __future__ import annotations

from datetime import datetime
from typing import Type

import backtrader as bt

from data.alpaca_data import fetch_daily_bars, fetch_minute_bars
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
    timeframe: str = "daily",
) -> float:
    """
    Orchestrate a full backtest run: fetch data, prepare it, wire it into Backtrader,
    and return the final portfolio value.

    Args:
        strategy_params: Optional dict of parameters to pass to the strategy
        slippage: Slippage percentage (e.g., 0.0005 for 0.05%)
        timeframe: Data timeframe - 'daily' or 'minute' (default: 'daily')

    Note: For minute timeframe strategies, both minute AND daily data are fetched.
          Daily data is used as a trend filter. Minute data is primary (datas[0]).
    """

    cerebro = bt.Cerebro(cheat_on_open=True)  # Enable next_open() callbacks

    # Fetch and add primary data based on timeframe
    if timeframe == "minute":
        # Fetch minute data (primary feed for entries/exits)
        print(f"Fetching minute data for {symbol}...")
        minute_df = fetch_minute_bars(symbol=symbol, start=start, end=end)
        print(f"Minute bars: {len(minute_df)} rows")

        minute_feed = df_to_bt_feed(minute_df)
        cerebro.adddata(minute_feed, name=symbol)  # datas[0]

        # Fetch daily data (for trend filter)
        print(f"Fetching daily data for {symbol} (trend filter)...")
        daily_df = fetch_daily_bars(symbol=symbol, start=start, end=end)
        print(f"Daily bars: {len(daily_df)} rows")

        daily_feed = df_to_bt_feed(daily_df)
        cerebro.adddata(daily_feed, name=f"{symbol}_daily")  # datas[1]

        print(f"Loaded: {len(minute_df)} minute bars + {len(daily_df)} daily bars")
    else:
        # Daily timeframe only
        print(f"Fetching daily data for {symbol}...")
        df = fetch_daily_bars(symbol=symbol, start=start, end=end)
        print(f"Daily bars: {len(df)} rows")

        data_feed = df_to_bt_feed(df)
        cerebro.adddata(data_feed, name=symbol)

    # Add strategy
    if strategy_params:
        cerebro.addstrategy(strategy, **strategy_params)
    else:
        cerebro.addstrategy(strategy)

    # Configure broker
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)
    cerebro.broker.set_slippage_perc(slippage)

    print(f"Starting value: ${cerebro.broker.getvalue():,.2f}")

    # Run backtest
    cerebro.run()

    final_value = float(cerebro.broker.getvalue())
    print(f"Final value: ${final_value:,.2f}")

    return final_value

