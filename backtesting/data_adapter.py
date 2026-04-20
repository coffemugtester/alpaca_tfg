from __future__ import annotations

from typing import Final

import backtrader as bt
import pandas as pd


_BT_COLUMNS: Final[tuple[str, ...]] = ("open", "high", "low", "close", "volume")


def df_to_bt_feed(df: pd.DataFrame) -> bt.feeds.PandasData:
    """
    Convert a price/volume DataFrame into a Backtrader PandasData feed.

    Expects at least the standard OHLCV columns and a DatetimeIndex.
    """

    df_bt = df.loc[:, _BT_COLUMNS].copy()

    # Backtrader expects a naive DatetimeIndex
    index = df_bt.index
    if getattr(index, "tz", None) is not None:
        df_bt.index = index.tz_convert(None)

    # Add explicit date parameters to ensure proper data feed configuration
    # This is required for next_open() callbacks to work correctly with COC mode
    return bt.feeds.PandasData(
        dataname=df_bt,
        fromdate=df_bt.index[0],
        todate=df_bt.index[-1],
    )

