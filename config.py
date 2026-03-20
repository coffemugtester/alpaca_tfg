from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

from alpaca.data.historical import StockHistoricalDataClient

from local_settings import alpaca_paper


# Public defaults for backtests
CASH_DEFAULT: Final[float] = 10_000.0
COMMISSION_DEFAULT: Final[float] = 0.0


def parse_date(date_str: str) -> datetime:
    """
    Parse a date string in YYYY-MM-DD format to a timezone-aware datetime.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Timezone-aware datetime object (UTC)
    """
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def get_alpaca_client() -> StockHistoricalDataClient:
    """
    Factory for an authenticated Alpaca historical data client.

    Keeping this behind a function makes it easy to swap credentials,
    environments, or provide a fake client in tests.
    """

    return StockHistoricalDataClient(
        alpaca_paper["api_key"],
        alpaca_paper["api_secret"],
    )

