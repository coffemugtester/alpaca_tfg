"""
Command controllers for CLI subcommands.

Each command handler receives parsed arguments and orchestrates the appropriate
backtesting workflow.
"""

import argparse
from argparse import Namespace

import matplotlib

from backtesting.runner import run_backtest
from backtesting.validation import ValidationPipeline
from backtesting.strategy_comparison import run_strategy_comparison, print_summary_table
from config import (
    CASH_DEFAULT,
    COMMISSION_DEFAULT,
    SLIPPAGE_DEFAULT,
    calculate_months_between,
)
from strategies.dca import DollarCostAveraging
from strategies.buy_and_hold import BuyAndHold
from strategies.tacticalmonthly import TacticalMonthlyRedistributed
from strategies.tacticalatrmonthly import TacticalAtrMonthly
from strategies.intraday_volatility_bands import IntradayVolatilityBands


# Canonical strategy registry - single source of truth
# Maps CLI names (lowercase) to (display name, strategy class, timeframe) tuples
# Timeframe: 'daily' or 'minute'
STRATEGY_REGISTRY = {
    "dca": ("DCA", DollarCostAveraging, "daily"),
    "bnh": ("Buy & Hold", BuyAndHold, "daily"),
    "tacticalmonthly": ("DCA Táctico", TacticalMonthlyRedistributed, "daily"),
    "tacticalatrmonthly": ("Corrección Táctica", TacticalAtrMonthly, "daily"),
    "intradayvol": ("Intraday Vol Bands", IntradayVolatilityBands, "minute"),
}

# Default assets for multi-asset comparison mode
DEFAULT_ASSETS = [
    # Indices & ETFs
    "SPY", "QQQ", "IWM", "GLD", "TLT", "XLE",
    # Tech
    "AAPL", "AMD",
    # Travel Services
    "BKNG", "RCL", "CCL", "EXPE", "NCLH",
    "MMYT", "TNL", "LIND", "TRIP",
]


def get_strategy_class(strategy_name: str):
    """Get a single strategy class by CLI name (e.g., 'dca' -> DollarCostAveraging)."""
    _display_name, strategy_cls, _timeframe = STRATEGY_REGISTRY[strategy_name]
    return strategy_cls


def get_strategy_timeframe(strategy_name: str) -> str:
    """Get the required timeframe for a strategy ('daily' or 'minute')."""
    _display_name, _strategy_cls, timeframe = STRATEGY_REGISTRY[strategy_name]
    return timeframe


def get_strategy_map():
    """Get all registered strategies as {display_name: strategy_class} dict."""
    return {
        display_name: strategy_cls
        for display_name, strategy_cls, _timeframe in STRATEGY_REGISTRY.values()
    }


def get_strategy_map_with_timeframes():
    """Get all registered strategies as {display_name: (strategy_class, timeframe)} dict."""
    return {
        display_name: (strategy_cls, timeframe)
        for display_name, strategy_cls, timeframe in STRATEGY_REGISTRY.values()
    }


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser with all subcommands."""
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

    # ============================================================
    # Subcommand: analyze-volatility
    # Analyze volatility metrics across multiple assets
    # ============================================================
    volatility_parser = subparsers.add_parser(
        "analyze-volatility",
        help="Analyze intraday volatility metrics across multiple assets",
    )
    volatility_parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        default=None,
        help=f"List of ticker symbols (default: {', '.join(DEFAULT_ASSETS)})",
    )
    volatility_parser.add_argument(
        "--start",
        type=str,
        default="2016-01-01",
        help="Start date in YYYY-MM-DD format (default: 2016-01-01)",
    )
    volatility_parser.add_argument(
        "--end",
        type=str,
        default="2026-01-01",
        help="End date in YYYY-MM-DD format (default: 2026-01-01)",
    )

    return parser


def handle_single_command(
    args: Namespace,
    strategy_cls,
    start,
    end,
):
    """
    Handle the 'single' subcommand: run one strategy on one asset.

    Args:
        args: Parsed command-line arguments
        strategy_cls: Strategy class to run
        start: Start datetime
        end: End datetime
    """
    # Set matplotlib backend based on --plot flag
    if not args.plot:
        matplotlib.use("Agg")

    # Get strategy timeframe
    timeframe = get_strategy_timeframe(args.strategy)

    # Calculate strategy-specific parameters
    strategy_params = {}
    num_months = calculate_months_between(start, end)

    if args.strategy == "dca":
        monthly_invest = args.cash / num_months
        strategy_params = {"monthly_invest": monthly_invest}
    # BuyAndHold, TacticalMonthly, TacticalATRMonthly, IntradayVolatilityBands don't need special params

    run_backtest(
        symbol=args.symbol,
        start=start,
        end=end,
        strategy=strategy_cls,
        cash=args.cash,
        commission=args.commission,
        slippage=args.slippage,
        strategy_params=strategy_params if strategy_params else None,
        timeframe=timeframe,
    )


def handle_compare_single_command(
    args: Namespace,
    strategies: dict,
    start,
    end,
):
    """
    Handle the 'compare-single' subcommand: compare all strategies on one asset.

    Args:
        args: Parsed command-line arguments
        strategies: Dict mapping strategy display names to strategy classes
        start: Start datetime
        end: End datetime
    """
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


def handle_compare_multi_command(
    args: Namespace,
    strategies: dict,
    start,
    end,
    default_assets: list[str],
):
    """
    Handle the 'compare-multi' subcommand: compare all strategies across multiple assets.

    Args:
        args: Parsed command-line arguments
        strategies: Dict mapping strategy display names to strategy classes (legacy)
        start: Start datetime
        end: End datetime
        default_assets: List of default asset symbols to use if --symbols not provided
    """
    # Determine which symbols to run
    if args.symbols is None:
        symbols = default_assets
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

    # Get strategies with their timeframes
    strategies_with_timeframes = get_strategy_map_with_timeframes()

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
            strategies_with_timeframes=strategies_with_timeframes,
        )
        all_results.append(result)

    # Print summary table if multiple assets
    if len(symbols) > 1:
        print_summary_table(all_results)


def handle_analyze_volatility_command(
    args: Namespace,
    start,
    end,
    default_assets: list[str],
):
    """
    Handle the 'analyze-volatility' subcommand: analyze intraday volatility across multiple assets.

    Args:
        args: Parsed command-line arguments
        start: Start datetime
        end: End datetime
        default_assets: List of default asset symbols to use if --symbols not provided
    """
    from data.volatility_analyzer import analyze_symbol_volatility
    from data.volatility_export import export_volatility_to_csv, print_volatility_summary_table

    # Determine which symbols to analyze
    if args.symbols is None:
        symbols = default_assets
        print(
            f"\nNo --symbols specified. Analyzing volatility for {len(symbols)} default assets:"
        )
        print(f"{', '.join(symbols)}\n")
    else:
        symbols = args.symbols

    # Analyze volatility for each symbol
    all_results = []
    for symbol in symbols:
        results = analyze_symbol_volatility(
            symbol=symbol,
            start=start,
            end=end,
        )
        if results:
            all_results.append(results)
            # Export results for this symbol
            export_volatility_to_csv(results)

    # Print summary table
    print_volatility_summary_table(all_results)
