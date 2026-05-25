"""
SQLite caching layer for Alpaca Markets historical data.

Provides transparent caching to eliminate redundant API calls across backtest runs.
Historical OHLCV data is immutable, so cache forever strategy is used.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


class AlpacaCache:
    """SQLite cache for Alpaca historical OHLCV data."""

    def __init__(self, db_path: str = "./data/alpaca_cache.db"):
        """
        Initialize database connection and create tables if needed.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create tables on first run
        self._init_db()

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Daily bars table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_bars (
                symbol TEXT NOT NULL,
                date DATE NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                PRIMARY KEY (symbol, date)
            )
        """)

        # Index for fast queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_symbol_date
            ON daily_bars(symbol, date)
        """)

        # Minute bars table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS minute_bars (
                symbol TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                PRIMARY KEY (symbol, timestamp)
            )
        """)

        # Index for fast queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_minute_symbol_timestamp
            ON minute_bars(symbol, timestamp)
        """)

        conn.commit()
        conn.close()

    def query_daily_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """
        Query daily bars from cache.

        Args:
            symbol: Stock ticker
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with OHLCV data if complete range cached, None otherwise
        """
        conn = sqlite3.connect(self.db_path)

        # Query cached data
        query = """
            SELECT date, open, high, low, close, volume
            FROM daily_bars
            WHERE symbol = ? AND date >= ? AND date <= ?
            ORDER BY date
        """

        df = pd.read_sql_query(
            query,
            conn,
            params=(symbol, start.date(), end.date()),
            parse_dates=['date'],
            index_col='date'
        )

        conn.close()

        if df.empty:
            return None

        # Filter out NaT (Not a Time) values that cause Backtrader errors
        df = df[df.index.notna()]

        if df.empty:
            return None

        # Check if cached data covers the full requested date range
        # Allow 5 days tolerance for weekends/recent trading days
        cached_start = df.index.min()
        cached_end = df.index.max()

        # Normalize all to timezone-naive for comparison
        if hasattr(cached_start, 'tz') and cached_start.tz is not None:
            cached_start = cached_start.tz_localize(None)
        if hasattr(cached_end, 'tz') and cached_end.tz is not None:
            cached_end = cached_end.tz_localize(None)

        # Convert start/end to pd.Timestamp and ensure timezone-naive
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        if start_ts.tz is not None:
            start_ts = start_ts.tz_localize(None)
        if end_ts.tz is not None:
            end_ts = end_ts.tz_localize(None)

        tolerance_days = pd.Timedelta(days=5)

        if cached_start > start_ts + tolerance_days:
            # Cache doesn't go back far enough
            return None

        if cached_end < end_ts - tolerance_days:
            # Cache doesn't go forward far enough
            return None

        # Check if we have complete data
        # Allow some tolerance for weekends/holidays
        # Expect ~252 trading days per year
        expected_rows = (end - start).days / 7 * 5  # Rough estimate
        actual_rows = len(df)

        # If we have at least 80% of expected rows, consider it complete
        # (accounts for holidays, market closures)
        if actual_rows < expected_rows * 0.8:
            return None

        return df

    def query_minute_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame | None:
        """
        Query minute bars from cache.

        Args:
            symbol: Stock ticker
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with OHLCV data if complete range cached, None otherwise
        """
        conn = sqlite3.connect(self.db_path)

        # Query cached data
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM minute_bars
            WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp
        """

        df = pd.read_sql_query(
            query,
            conn,
            params=(symbol, start, end),
            parse_dates=['timestamp'],
            index_col='timestamp'
        )

        conn.close()

        if df.empty:
            return None

        # Filter out NaT (Not a Time) values that cause Backtrader errors
        df = df[df.index.notna()]

        if df.empty:
            return None

        # Check if cached data covers the full requested date range
        # Allow 5 days tolerance for weekends/recent trading days
        cached_start = df.index.min()
        cached_end = df.index.max()

        # Normalize all to timezone-naive for comparison
        if hasattr(cached_start, 'tz') and cached_start.tz is not None:
            cached_start = cached_start.tz_localize(None)
        if hasattr(cached_end, 'tz') and cached_end.tz is not None:
            cached_end = cached_end.tz_localize(None)

        # Convert start/end to pd.Timestamp and ensure timezone-naive
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        if start_ts.tz is not None:
            start_ts = start_ts.tz_localize(None)
        if end_ts.tz is not None:
            end_ts = end_ts.tz_localize(None)

        tolerance_days = pd.Timedelta(days=5)

        if cached_start > start_ts + tolerance_days:
            # Cache doesn't go back far enough
            return None

        if cached_end < end_ts - tolerance_days:
            # Cache doesn't go forward far enough
            return None

        # Check if we have reasonable data coverage
        # Market hours: 6.5 hours/day * 60 min = 390 bars/day
        # Estimate based on trading days (~252/year = 69% of calendar days)
        total_days = (end - start).days
        trading_days_estimate = total_days * 0.69  # ~252 trading days per 365 calendar days
        expected_bars = trading_days_estimate * 390 * 0.5  # 50% of theoretical (accounts for data gaps, early closes)
        actual_bars = len(df)

        # If we have at least 40% of expected bars, consider it complete
        # Lower threshold for minute data due to historical data availability limitations
        if actual_bars < expected_bars * 0.4:
            return None

        return df

    def insert_daily_bars(self, symbol: str, df: pd.DataFrame) -> None:
        """
        Bulk insert daily bars into cache.

        Args:
            symbol: Stock ticker
            df: DataFrame with DatetimeIndex and OHLCV columns
        """
        if df.empty:
            return

        conn = sqlite3.connect(self.db_path)

        # Prepare data for insert
        df_copy = df.copy()
        df_copy['symbol'] = symbol
        # Convert to timezone-naive UTC before storing to ensure uniqueness
        # Handle both timezone-aware and timezone-naive inputs
        idx = pd.to_datetime(df_copy.index)
        if idx.tz is not None:
            # Timezone-aware: convert to UTC then strip timezone
            df_copy['date'] = idx.tz_convert('UTC').tz_localize(None)
        else:
            # Already timezone-naive: use as-is
            df_copy['date'] = idx

        # Select columns in correct order
        insert_df = df_copy[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']]

        # Convert Timestamp column to Python date objects for SQLite compatibility
        # Must convert to list to prevent pandas from re-converting to Timestamp
        insert_df = insert_df.copy()
        insert_df['date'] = [
            x.date() if hasattr(x, 'date') else x
            for x in insert_df['date']
        ]

        # Insert in batches to avoid SQLite's 999 variable limit
        # With 7 columns, max rows per batch = 999/7 = ~142
        # Use INSERT OR REPLACE to handle duplicates gracefully
        batch_size = 140
        cursor = conn.cursor()

        for i in range(0, len(insert_df), batch_size):
            batch = insert_df.iloc[i:i + batch_size]

            # Use INSERT OR REPLACE for each row
            for _, row in batch.iterrows():
                # Convert date to Python date at insertion time
                row_values = (
                    row['symbol'],
                    row['date'].date() if hasattr(row['date'], 'date') else row['date'],
                    row['open'],
                    row['high'],
                    row['low'],
                    row['close'],
                    row['volume']
                )
                cursor.execute("""
                    INSERT OR REPLACE INTO daily_bars
                    (symbol, date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, row_values)

        conn.commit()
        conn.close()

    def insert_minute_bars(self, symbol: str, df: pd.DataFrame) -> None:
        """
        Bulk insert minute bars into cache.

        Args:
            symbol: Stock ticker
            df: DataFrame with DatetimeIndex and OHLCV columns
        """
        if df.empty:
            return

        conn = sqlite3.connect(self.db_path)

        # Prepare data for insert
        df_copy = df.copy()
        df_copy['symbol'] = symbol
        # Convert to timezone-naive UTC before storing to ensure uniqueness
        # Handle both timezone-aware and timezone-naive inputs
        idx = pd.to_datetime(df_copy.index)
        if idx.tz is not None:
            # Timezone-aware: convert to UTC then strip timezone
            df_copy['timestamp'] = idx.tz_convert('UTC').tz_localize(None)
        else:
            # Already timezone-naive: use as-is
            df_copy['timestamp'] = idx

        # Select columns in correct order
        insert_df = df_copy[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]

        # Convert Timestamp column to Python datetime objects for SQLite compatibility
        # Must convert to list to prevent pandas from re-converting to Timestamp
        insert_df = insert_df.copy()
        insert_df['timestamp'] = [
            x.to_pydatetime() if hasattr(x, 'to_pydatetime') else x
            for x in insert_df['timestamp']
        ]

        # Insert in batches to avoid SQLite's 999 variable limit
        # With 7 columns, max rows per batch = 999/7 = ~142
        # Use INSERT OR REPLACE to handle duplicates gracefully
        batch_size = 140
        total_rows = len(insert_df)
        cursor = conn.cursor()

        print(f"Inserting {total_rows:,} minute bars with duplicate handling...")

        for i in range(0, total_rows, batch_size):
            batch = insert_df.iloc[i:i + batch_size]

            # Use INSERT OR REPLACE for each row
            for _, row in batch.iterrows():
                # Convert timestamp to Python datetime at insertion time
                row_values = (
                    row['symbol'],
                    row['timestamp'].to_pydatetime() if hasattr(row['timestamp'], 'to_pydatetime') else row['timestamp'],
                    row['open'],
                    row['high'],
                    row['low'],
                    row['close'],
                    row['volume']
                )
                cursor.execute("""
                    INSERT OR REPLACE INTO minute_bars
                    (symbol, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, row_values)

            # Progress indicator for large datasets
            if (i + batch_size) % 50000 == 0 or i + batch_size >= total_rows:
                progress = min(i + batch_size, total_rows)
                print(f"  Progress: {progress:,}/{total_rows:,} rows ({progress/total_rows*100:.1f}%)")

        conn.commit()
        conn.close()
        print(f"Successfully cached {total_rows:,} minute bars for {symbol}")

    def get_cached_date_range(
        self,
        symbol: str,
        timeframe: str = "daily"
    ) -> tuple[datetime | None, datetime | None]:
        """
        Get the date range of cached data for a symbol.

        Args:
            symbol: Stock ticker
            timeframe: 'daily' or 'minute'

        Returns:
            Tuple of (min_date, max_date) or (None, None) if no data
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if timeframe == "daily":
            query = """
                SELECT MIN(date), MAX(date)
                FROM daily_bars
                WHERE symbol = ?
            """
        else:
            query = """
                SELECT MIN(timestamp), MAX(timestamp)
                FROM minute_bars
                WHERE symbol = ?
            """

        cursor.execute(query, (symbol,))
        result = cursor.fetchone()
        conn.close()

        if result and result[0] and result[1]:
            min_date = pd.to_datetime(result[0])
            max_date = pd.to_datetime(result[1])
            return (min_date, max_date)

        return (None, None)
