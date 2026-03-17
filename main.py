from datetime import datetime, timezone
import argparse

from backtesting.runner import run_backtest
from config import CASH_DEFAULT, COMMISSION_DEFAULT
from strategies.dca import DollarCostAveraging
from strategies.buy_and_hold import BuyAndHold


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a backtest with configurable symbol, date range, and strategy."
    )

    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Ticker symbol to analyze, e.g. SPY, QQQ, AAPL",
    )

    parser.add_argument(
        "--start", type=str, required=True, help="Start date in YYYY-MM-DD format"
    )

    parser.add_argument(
        "--end", type=str, required=True, help="End date in YYYY-MM-DD format"
    )

    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        choices=["dca", "bnh"],
        help="Strategy to run",
    )

    parser.add_argument(
        "--cash", type=float, default=CASH_DEFAULT, help="Initial cash for the backtest"
    )

    parser.add_argument(
        "--commission",
        type=float,
        default=COMMISSION_DEFAULT,
        help="Commission rate",
    )

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def get_strategy_class(strategy_name: str):
    strategy_map = {
        "dca": DollarCostAveraging,
        "bnh": BuyAndHold,
    }
    return strategy_map[strategy_name]


def main():
    args = parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end)

    if start >= end:
        raise ValueError("Start date must be earlier than end date.")

    strategy_cls = get_strategy_class(args.strategy)

    run_backtest(
        symbol=args.symbol,
        start=start,
        end=end,
        strategy=strategy_cls,
        cash=args.cash,
        commission=args.commission,
    )


if __name__ == "__main__":
    main()
