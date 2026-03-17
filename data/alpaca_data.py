from __future__ import annotations

from datetime import datetime

import pandas as pd
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config import get_alpaca_client


def fetch_daily_bars(
    symbol: str,
    start: datetime,
    end: datetime,
    adjustment: str = "raw",
) -> pd.DataFrame:
    """
    Fetch daily bars for a single symbol from Alpaca and return a clean DataFrame.
    """

    client = get_alpaca_client()

    request = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        adjustment=adjustment,
    )

    bars = client.get_stock_bars(request)
    df = bars.df

    # If multiple symbols are returned, collapse the multi-index to just this symbol.
    if df.index.nlevels == 2:
        df = df.xs(symbol)

    return df
