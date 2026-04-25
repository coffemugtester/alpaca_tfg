import argparse

import matplotlib

from backtesting.runner import run_backtest
from backtesting.validation import ValidationPipeline
from backtesting.strategy_comparison import run_strategy_comparison, print_summary_table
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
from strategies.tacticaltrenddip import TacticalTrendDipStrategy
from strategies.tacticaldipcooldown import TacticalTrendDipCooldown
from strategies.tacticaldipcooldownbollinger import TacticalTrendDipCooldownBollinger
from strategies.tacticalagressive import TacticalAggressive
from strategies.tacticalatr import TacticalTrendDipReserve


# Canonical strategy registry - single source of truth
# Maps CLI names (lowercase) to (display name, strategy class) tuples
STRATEGY_REGISTRY = {
    "dca": ("DCA", DollarCostAveraging),
    "bnh": ("Buy & Hold", BuyAndHold),
    "trendfollowing": ("TrendFollowing", TrendFollowingStrategy),
    "meanreversion": ("MeanReversion", MeanReversionStrategy),
    "dinamica": ("Dinámica", DinamicaStrategy),
    "tacticaltrenddip": ("TacticalTrendDip", TacticalTrendDipStrategy),
    "tacticaldipcooldown": ("TacticalDipCooldwn", TacticalTrendDipCooldown),
    "tacticaldipcooldownbollinger": (
        "TacticalDipCooldwnBollinger",
        TacticalTrendDipCooldownBollinger,
    ),
    "tacticalagressive": ("TacticalAggressive", TacticalAggressive),
    "tacticalatr": ("TacticalATR", TacticalTrendDipReserve),
}

# Default assets for multi-asset comparison mode
DEFAULT_ASSETS = ["SPY", "QQQ", "IWM", "GLD", "TLT", "AAPL", "AMD", "XLE"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run backtests with configurable symbols, date range, and strategies."
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Command to run"
    )

    # ============================================================
    # Subcommand: single
    # Run a single strategy on a single asset
    # ============================================================
    single_parser = subparsers.add_parser(
        "single",
        help="Run a single strategy on a single asset",
    )
    single_parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Ticker symbol to analyze, e.g. SPY, QQQ, AAPL",
    )
    single_parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        choices=list(STRATEGY_REGISTRY.keys()),
        help="Strategy to run",
    )
    single_parser.add_argument(
        "--plot",
        action="store_true",
        help="Show matplotlib plot at end",
    )
    single_parser.add_argument(
        "--start",
        type=str,
        default="2016-01-01",
        help="Start date in YYYY-MM-DD format (default: 2016-01-01)",
    )
    single_parser.add_argument(
        "--end",
        type=str,
        default="2026-01-01",
        help="End date in YYYY-MM-DD format (default: 2026-01-01)",
    )
    single_parser.add_argument(
        "--cash", type=float, default=CASH_DEFAULT, help="Initial cash for the backtest"
    )
    single_parser.add_argument(
        "--commission",
        type=float,
        default=COMMISSION_DEFAULT,
        help="Commission percentage (default: 0.02%%)",
    )
    single_parser.add_argument(
        "--slippage",
        type=float,
        default=SLIPPAGE_DEFAULT,
        help="Slippage percentage (default: 0.03%%)",
    )

    # ============================================================
    # Subcommand: compare-single
    # Compare all strategies on a single asset
    # ============================================================
    compare_single_parser = subparsers.add_parser(
        "compare-single",
        help="Compare all registered strategies on a single asset",
    )
    compare_single_parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Ticker symbol to analyze, e.g. SPY, QQQ, AAPL",
    )
    compare_single_parser.add_argument(
        "--start",
        type=str,
        default="2016-01-01",
        help="Start date in YYYY-MM-DD format (default: 2016-01-01)",
    )
    compare_single_parser.add_argument(
        "--end",
        type=str,
        default="2026-01-01",
        help="End date in YYYY-MM-DD format (default: 2026-01-01)",
    )
    compare_single_parser.add_argument(
        "--cash", type=float, default=CASH_DEFAULT, help="Initial cash for the backtest"
    )
    compare_single_parser.add_argument(
        "--commission",
        type=float,
        default=COMMISSION_DEFAULT,
        help="Commission percentage (default: 0.02%%)",
    )
    compare_single_parser.add_argument(
        "--slippage",
        type=float,
        default=SLIPPAGE_DEFAULT,
        help="Slippage percentage (default: 0.03%%)",
    )

    # ============================================================
    # Subcommand: compare-multi
    # Compare all strategies across multiple assets
    # ============================================================
    compare_multi_parser = subparsers.add_parser(
        "compare-multi",
        help="Compare all registered strategies across multiple assets",
    )
    compare_multi_parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        default=None,
        help=f"List of ticker symbols (default: {', '.join(DEFAULT_ASSETS)})",
    )
    compare_multi_parser.add_argument(
        "--plot",
        action="store_true",
        help="Show matplotlib plots (disabled in multi-asset mode)",
    )
    compare_multi_parser.add_argument(
        "--start",
        type=str,
        default="2016-01-01",
        help="Start date in YYYY-MM-DD format (default: 2016-01-01)",
    )
    compare_multi_parser.add_argument(
        "--end",
        type=str,
        default="2026-01-01",
        help="End date in YYYY-MM-DD format (default: 2026-01-01)",
    )
    compare_multi_parser.add_argument(
        "--cash", type=float, default=CASH_DEFAULT, help="Initial cash for the backtest"
    )
    compare_multi_parser.add_argument(
        "--commission",
        type=float,
        default=COMMISSION_DEFAULT,
        help="Commission percentage (default: 0.02%%)",
    )
    compare_multi_parser.add_argument(
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

    # Parse dates
    start = parse_date(args.start)
    end = parse_date(args.end)

    if start >= end:
        raise ValueError("Start date must be earlier than end date.")

    # Route based on subcommand
    if args.command == "single":
        # ============================================================
        # Single-strategy mode: run one strategy on one asset
        # ============================================================

        # Set matplotlib backend based on --plot flag
        if not args.plot:
            matplotlib.use("Agg")

        strategy_cls = get_strategy_class(args.strategy)

        # Calculate strategy-specific parameters
        strategy_params = {}
        num_months = calculate_months_between(start, end)

        if args.strategy == "dca":
            monthly_invest = args.cash / num_months
            strategy_params = {"monthly_invest": monthly_invest}
        elif args.strategy == "dinamica":
            monthly_invest = args.cash / num_months
            strategy_params = {"monthly_invest": monthly_invest}
        elif args.strategy in ["trendfollowing", "meanreversion"]:
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

    elif args.command == "compare-single":
        # ============================================================
        # Compare-single mode: run all strategies on one asset
        # ============================================================
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

    elif args.command == "compare-multi":
        # ============================================================
        # Compare-multi mode: run all strategies on multiple assets
        # ============================================================

        # Determine which symbols to run
        if args.symbols is None:
            symbols = DEFAULT_ASSETS
            print(
                f"\nNo --symbols specified. Running comparison for {len(symbols)} default assets:"
            )
            print(f"{', '.join(symbols)}\n")
        else:
            symbols = args.symbols

        # Force disable plots in multi-asset mode
        show_plots = args.plot
        if len(symbols) > 1 and args.plot:
            print(
                "WARNING: --plot flag ignored in multi-asset mode (too many windows)\n"
            )
            show_plots = False

        # Get strategy map
        strategies = get_strategy_map()

        # Run comparison for each symbol
        all_results = []
        for symbol in symbols:
            result = run_strategy_comparison(
                symbol=symbol,
                start=start,
                end=end,
                cash=args.cash,
                commission=args.commission,
                slippage=args.slippage,
                show_plots=show_plots,
                strategies=strategies,
            )
            all_results.append(result)

        # Print summary table if multiple assets
        if len(symbols) > 1:
            print_summary_table(all_results)


if __name__ == "__main__":
    main()
