from __future__ import annotations

from typing import Final

from alpaca.data.historical import StockHistoricalDataClient

from local_settings import alpaca_paper


# Public defaults for backtests
CASH_DEFAULT: Final[float] = 10_000.0
COMMISSION_DEFAULT: Final[float] = 0.0


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

