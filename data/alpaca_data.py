from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config import get_alpaca_client


def fetch_daily_bars(
    symbol: str,
    start: datetime,
    end: datetime,
    adjustment: str = "split",
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


def fetch_minute_bars(
    symbol: str,
    start: datetime,
    end: datetime,
    adjustment: str = "split",
) -> pd.DataFrame:
    """
    Fetch minute bars for a single symbol from Alpaca and return a clean DataFrame.

    Handles pagination for large date ranges (Alpaca limits to 10,000 bars per request).
    For 10-year periods, this may require multiple requests.

    Args:
        symbol: Ticker symbol
        start: Start datetime
        end: End datetime
        adjustment: Price adjustment type (default: "split")

    Returns:
        DataFrame with OHLCV data at minute resolution

    Note:
        Alpaca's historical minute data availability may be limited (typically 1-5 years).
        If data is unavailable for the full period, returns whatever is available.
    """
    client = get_alpaca_client()

    # Strategy: Fetch data in chunks to handle pagination
    # Alpaca allows 10K bars per request
    # ~390 minutes per trading day → ~25 trading days per request max
    # We'll fetch in 1-month chunks to be safe

    all_data = []
    current_start = start

    while current_start < end:
        # Fetch next chunk (1 month at a time)
        chunk_end = min(current_start + timedelta(days=30), end)

        try:
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Minute,
                start=current_start,
                end=chunk_end,
                adjustment=adjustment,
            )

            bars = client.get_stock_bars(request)
            df_chunk = bars.df

            # Handle multi-index if present
            if df_chunk.index.nlevels == 2:
                df_chunk = df_chunk.xs(symbol)

            if not df_chunk.empty:
                all_data.append(df_chunk)
                print(f"Fetched {len(df_chunk)} minute bars for {symbol} ({current_start.date()} to {chunk_end.date()})")
            else:
                print(f"No data available for {symbol} ({current_start.date()} to {chunk_end.date()})")

        except Exception as e:
            print(f"ERROR fetching {symbol} ({current_start.date()} to {chunk_end.date()}): {e}")

        # Move to next chunk
        current_start = chunk_end

    if not all_data:
        print(f"WARNING: No minute data available for {symbol} in period {start.date()} to {end.date()}")
        return pd.DataFrame()

    # Concatenate all chunks
    df = pd.concat(all_data)
    df = df.sort_index()

    # Remove duplicates if any (can happen at chunk boundaries)
    df = df[~df.index.duplicated(keep='first')]

    print(f"Total: {len(df)} minute bars for {symbol}")
    return df
