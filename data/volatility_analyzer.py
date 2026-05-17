"""
Volatility analysis module for intraday (minute-level) data.

Calculates volatility metrics including standard deviation, annualized volatility,
and Average True Range (ATR) for overall periods and semester breakdowns.
"""

from datetime import datetime, timezone
from typing import Optional
import numpy as np
import pandas as pd

from data.alpaca_data import fetch_minute_bars


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate Average True Range (ATR) for the given OHLC data.

    Args:
        df: DataFrame with high, low, close columns
        period: Number of periods for ATR calculation (default: 14)

    Returns:
        Current ATR value (latest in the series)
    """
    if len(df) < period:
        return 0.0

    high = df['high']
    low = df['low']
    close = df['close']

    # True Range is the maximum of:
    # 1. Current High - Current Low
    # 2. abs(Current High - Previous Close)
    # 3. abs(Current Low - Previous Close)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR is the moving average of True Range
    atr_series = true_range.rolling(window=period).mean()

    # Return the most recent ATR value
    return float(atr_series.iloc[-1]) if not atr_series.empty else 0.0


def calculate_volatility_metrics(df: pd.DataFrame) -> dict:
    """
    Calculate volatility metrics from minute-level OHLCV data.

    Args:
        df: DataFrame with OHLCV data (must have 'close', 'high', 'low' columns)

    Returns:
        Dict with:
            - daily_vol_std: Standard deviation of minute returns
            - annualized_vol: Annualized volatility (std * sqrt(trading_minutes_per_year))
            - atr_14: 14-period Average True Range
            - atr_pct: ATR as percentage of current price
            - avg_close: Average closing price in period
    """
    if df.empty or len(df) < 30:
        return {
            "daily_vol_std": 0.0,
            "annualized_vol": 0.0,
            "atr_14": 0.0,
            "atr_pct": 0.0,
            "avg_close": 0.0,
        }

    # Calculate minute-level returns
    returns = df['close'].pct_change().dropna()

    # Standard deviation of returns (minute-level volatility)
    vol_std = float(returns.std()) if len(returns) > 0 else 0.0

    # Annualize the volatility
    # Assumption: 390 trading minutes per day, 252 trading days per year
    # Total trading minutes per year = 390 * 252 = 98,280
    # But since we're working with minute bars, we use sqrt(98280) for annualization
    trading_minutes_per_year = 390 * 252
    annualized_vol = vol_std * np.sqrt(trading_minutes_per_year) if vol_std > 0 else 0.0

    # Calculate ATR
    atr = calculate_atr(df, period=14)

    # Calculate ATR as percentage of current price
    avg_close = float(df['close'].mean())
    atr_pct = (atr / avg_close * 100) if avg_close > 0 else 0.0

    return {
        "daily_vol_std": vol_std,
        "annualized_vol": annualized_vol,
        "atr_14": atr,
        "atr_pct": atr_pct,
        "avg_close": avg_close,
    }


def break_into_semesters(start: datetime, end: datetime) -> list[tuple[datetime, datetime, str]]:
    """
    Break a date range into 6-month semesters.

    Args:
        start: Start date (timezone-aware)
        end: End date (timezone-aware)

    Returns:
        List of (start_date, end_date, label) tuples for each semester
        Label format: "YYYY-S1" or "YYYY-S2"
    """
    semesters = []
    current_year = start.year
    current_month = 1 if start.month <= 6 else 7

    # Get timezone from input (default to UTC if naive)
    tz = start.tzinfo if start.tzinfo else timezone.utc

    while True:
        # Determine semester boundaries (with same timezone as input)
        if current_month == 1:
            sem_start = datetime(current_year, 1, 1, tzinfo=tz)
            sem_end = datetime(current_year, 6, 30, 23, 59, 59, tzinfo=tz)
            label = f"{current_year}-S1"
        else:
            sem_start = datetime(current_year, 7, 1, tzinfo=tz)
            sem_end = datetime(current_year, 12, 31, 23, 59, 59, tzinfo=tz)
            label = f"{current_year}-S2"

        # Adjust boundaries to fit within requested range
        actual_start = max(sem_start, start)
        actual_end = min(sem_end, end)

        # Only add if there's meaningful overlap
        if actual_start < actual_end:
            semesters.append((actual_start, actual_end, label))

        # Move to next semester
        if current_month == 1:
            current_month = 7
        else:
            current_month = 1
            current_year += 1

        # Stop if we've passed the end date
        if sem_start >= end:
            break

    return semesters


def analyze_symbol_volatility(
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """
    Analyze volatility for a symbol across overall period and semesters.

    Args:
        symbol: Ticker symbol
        start: Start datetime
        end: End datetime

    Returns:
        List of result dicts, one for overall period + one per semester.
        Each dict contains:
            - asset: Symbol
            - period: Period label ("Overall" or "YYYY-SN")
            - period_type: "overall" or "semester"
            - start_date: Period start
            - end_date: Period end
            - daily_vol_std: Volatility std dev
            - annualized_vol: Annualized volatility
            - atr_14: Average True Range
            - atr_pct: ATR as % of price
    """
    print(f"\n{'='*80}")
    print(f"Analyzing volatility for {symbol}")
    print(f"Period: {start.date()} to {end.date()}")
    print(f"{'='*80}")

    # Fetch minute data for entire period
    df_full = fetch_minute_bars(symbol, start, end)

    if df_full.empty:
        print(f"ERROR: No data available for {symbol}")
        return []

    results = []

    # 1. Calculate overall metrics
    print(f"\nCalculating overall metrics...")
    overall_metrics = calculate_volatility_metrics(df_full)
    results.append({
        "asset": symbol,
        "period": "Overall",
        "period_type": "overall",
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "daily_vol_std": overall_metrics["daily_vol_std"],
        "annualized_vol": overall_metrics["annualized_vol"],
        "atr_14": overall_metrics["atr_14"],
        "atr_pct": overall_metrics["atr_pct"],
    })

    # 2. Calculate per-semester metrics
    semesters = break_into_semesters(start, end)
    print(f"Breaking down into {len(semesters)} semesters...")

    for sem_start, sem_end, label in semesters:
        # Filter data for this semester
        df_semester = df_full[(df_full.index >= sem_start) & (df_full.index <= sem_end)]

        if len(df_semester) < 30:
            print(f"  Skipping {label}: insufficient data ({len(df_semester)} bars)")
            continue

        sem_metrics = calculate_volatility_metrics(df_semester)
        results.append({
            "asset": symbol,
            "period": label,
            "period_type": "semester",
            "start_date": sem_start.strftime("%Y-%m-%d"),
            "end_date": sem_end.strftime("%Y-%m-%d"),
            "daily_vol_std": sem_metrics["daily_vol_std"],
            "annualized_vol": sem_metrics["annualized_vol"],
            "atr_14": sem_metrics["atr_14"],
            "atr_pct": sem_metrics["atr_pct"],
        })
        print(f"  {label}: Vol={sem_metrics['annualized_vol']:.3f} | ATR={sem_metrics['atr_14']:.2f}")

    print(f"\nCompleted analysis for {symbol}: {len(results)} periods")
    return results
