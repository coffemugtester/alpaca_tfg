import argparse

import matplotlib

from backtesting.runner import run_backtest
from backtesting.validation import ValidationPipeline
from config import (
    CASH_DEFAULT,
    COMMISSION_DEFAULT,
    SLIPPAGE_DEFAULT,
    parse_date,
    calculate_months_between,
)
from strategies.dca import DollarCostAveraging
from strategies.buy_and_hold import BuyAndHold
from strategies.trendfollow import TrendFollowingStrategy
from strategies.meanreversion import MeanReversionStrategy
from strategies.dinamica import DinamicaStrategy


# Canonical strategy registry - single source of truth
# Maps CLI names (lowercase) to (display name, strategy class) tuples
STRATEGY_REGISTRY = {
    "dca": ("DCA", DollarCostAveraging),
    "bnh": ("Buy & Hold", BuyAndHold),
    "trendfollowing": ("TrendFollowing", TrendFollowingStrategy),
    "meanreversion": ("MeanReversion", MeanReversionStrategy),
    "dinamica": ("Dinámica", DinamicaStrategy),
}


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
        "--start",
        type=str,
        default="2016-01-01",
        help="Start date in YYYY-MM-DD format (default: 2016-01-04)",
    )

    parser.add_argument(
        "--end",
        type=str,
        default="2026-01-01",
        help="End date in YYYY-MM-DD format (default: 2026-01-04)",
    )

    # Strategy selection for single-strategy mode
    parser.add_argument(
        "--strategy",
        type=str,
        choices=list(STRATEGY_REGISTRY.keys()),
        help="Strategy to run (single-strategy mode)",
    )

    # Comparison mode flag
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare all registered strategies (comparison mode)",
    )

    # Plot display flag (single-strategy mode only)
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Show matplotlib plot at end (single-strategy mode only)",
    )

    parser.add_argument(
        "--cash", type=float, default=CASH_DEFAULT, help="Initial cash for the backtest"
    )

    parser.add_argument(
        "--commission",
        type=float,
        default=COMMISSION_DEFAULT,
        help="Commission percentage (default: 0.02%%)",
    )

    parser.add_argument(
        "--slippage",
        type=float,
        default=SLIPPAGE_DEFAULT,
        help="Slippage percentage (default: 0.03%%)",
    )

    return parser.parse_args()


def get_strategy_class(strategy_name: str):
    """Get a single strategy class by CLI name (e.g., 'dca' -> DollarCostAveraging)."""
    _display_name, strategy_cls = STRATEGY_REGISTRY[strategy_name]
    return strategy_cls


def get_strategy_map():
    """Get all registered strategies as {display_name: strategy_class} dict."""
    return {
        display_name: strategy_cls
        for display_name, strategy_cls in STRATEGY_REGISTRY.values()
    }


def main():
    args = parse_args()

    # Validate arguments
    if args.compare and args.strategy:
        raise ValueError("Cannot use both --compare and --strategy. Choose one mode.")

    if not args.compare and not args.strategy:
        raise ValueError("Must specify either --strategy or --compare.")

    if args.plot and args.compare:
        raise ValueError(
            "--plot flag only works in single-strategy mode, not with --compare."
        )

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
            slippage=args.slippage,
        )
        pipeline.run_comparison()
    else:
        # Single-strategy mode: run one strategy

        # Set matplotlib backend based on --plot flag
        if not args.plot:
            # Suppress plots if --plot not specified
            matplotlib.use("Agg")
        # else: leave backend as default (interactive) to show plots

        strategy_cls = get_strategy_class(args.strategy)

        # Calculate strategy-specific parameters
        strategy_params = {}
        num_months = calculate_months_between(start, end)

        if args.strategy == "dca":
            # DCA spreads initial cash evenly over all months
            monthly_invest = args.cash / num_months
            strategy_params = {"monthly_invest": monthly_invest}
        elif args.strategy == "dinamica":
            # dinamica currently uses DCA baseline
            monthly_invest = args.cash / num_months
            strategy_params = {"monthly_invest": monthly_invest}
        elif args.strategy in ["trendfollowing", "meanreversion"]:
            # Dynamic redistribution strategies need total_months
            strategy_params = {"total_months": num_months}

        run_backtest(
            symbol=args.symbol,
            start=start,
            end=end,
            strategy=strategy_cls,
            cash=args.cash,
            commission=args.commission,
            slippage=args.slippage,
            strategy_params=strategy_params if strategy_params else None,
        )


if __name__ == "__main__":
    main()
