import argparse

from backtesting.runner import run_backtest
from backtesting.validation import ValidationPipeline
from config import CASH_DEFAULT, COMMISSION_DEFAULT, parse_date, calculate_months_between
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

    # Strategy selection for single-strategy mode
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["dca", "bnh"],
        help="Strategy to run (single-strategy mode)",
    )

    # Comparison mode flag
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare all registered strategies (comparison mode)",
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


def get_strategy_class(strategy_name: str):
    """Get a single strategy class by name."""
    strategy_map = {
        "dca": DollarCostAveraging,
        "bnh": BuyAndHold,
    }
    return strategy_map[strategy_name]


def get_strategy_map():
    """Get all registered strategies."""
    return {
        "DCA": DollarCostAveraging,
        "Buy & Hold": BuyAndHold,
    }


def main():
    args = parse_args()

    # Validate arguments
    if args.compare and args.strategy:
        raise ValueError("Cannot use both --compare and --strategy. Choose one mode.")

    if not args.compare and not args.strategy:
        raise ValueError("Must specify either --strategy or --compare.")

    # Parse dates
    start = parse_date(args.start)
    end = parse_date(args.end)

    if start >= end:
        raise ValueError("Start date must be earlier than end date.")

    # Run in comparison mode or single-strategy mode
    if args.compare:
        # Comparison mode: run all strategies
        strategies = get_strategy_map()
        pipeline = ValidationPipeline(
            strategies=strategies,
            symbol=args.symbol,
            start=start,
            end=end,
            cash=args.cash,
            commission=args.commission,
        )
        pipeline.run_comparison()
    else:
        # Single-strategy mode: run one strategy
        strategy_cls = get_strategy_class(args.strategy)

        # Calculate strategy-specific parameters
        strategy_params = {}
        if args.strategy == "dca":
            # DCA spreads initial cash evenly over all months
            num_months = calculate_months_between(start, end)
            monthly_invest = args.cash / num_months
            strategy_params = {"monthly_invest": monthly_invest}

        run_backtest(
            symbol=args.symbol,
            start=start,
            end=end,
            strategy=strategy_cls,
            cash=args.cash,
            commission=args.commission,
            strategy_params=strategy_params if strategy_params else None,
        )


if __name__ == "__main__":
    main()
