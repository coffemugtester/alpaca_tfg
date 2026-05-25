"""
Command controllers for CLI subcommands.

Each command handler receives parsed arguments and orchestrates the appropriate
backtesting workflow.
"""

import argparse
import os
import shutil
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from argparse import Namespace
from datetime import datetime

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
from strategies.tactical_volume_dca import TacticalVolumeDCA


# Canonical strategy registry - single source of truth
# Maps CLI names (lowercase) to (display name, strategy class, timeframe) tuples
# Timeframe: 'daily' or 'minute'
STRATEGY_REGISTRY = {
    "dca": ("DCA", DollarCostAveraging, "daily"),
    "bnh": ("Buy & Hold", BuyAndHold, "daily"),
    # "tacticalmonthly": ("DCA Táctico", TacticalMonthlyRedistributed, "daily"),  # DEPRECATED: Replaced by volumecorrdca
    "tacticalatrmonthly": ("Corrección Táctica", TacticalAtrMonthly, "daily"),
    "intradayvol": ("Intraday Vol Bands", IntradayVolatilityBands, "minute"),
    "volumecorrdca": ("Volume Correction DCA", TacticalVolumeDCA, "minute"),
}

# Default assets for multi-asset comparison mode
DEFAULT_ASSETS = [
    # Indices & ETFs
    "SPY",
    "QQQ",
    "IWM",
    "GLD",
    "TLT",
    "XLE",
    # Tech
    "AAPL",
    "AMD",
    # Travel Services
    "BKNG",
    "RCL",
    "CCL",
    "EXPE",
    "NCLH",
    "MMYT",
    "TNL",
    "LIND",
    "TRIP",
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
    compare_multi_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run backtests in parallel (faster for multiple symbols)",
    )
    compare_multi_parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force refresh data from API, bypassing cache",
    )
    compare_multi_parser.add_argument(
        "--strategies",
        type=str,
        nargs="+",
        default=None,
        help=f"List of strategy keys to run (default: all). Available: {', '.join(STRATEGY_REGISTRY.keys())}",
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


def _run_single_symbol_backtest(
    symbol: str,
    start,
    end,
    cash: float,
    commission: float,
    slippage: float,
    strategies_with_timeframes: dict,
):
    """
    Worker function to run strategies for a single symbol (module-level for pickling).

    Args:
        symbol: Ticker symbol
        start: Start datetime
        end: End datetime
        cash: Initial cash
        commission: Commission rate
        slippage: Slippage rate
        strategies_with_timeframes: Strategy registry

    Returns:
        Result dict or None on failure
    """
    symbol_start = time.time()
    try:
        print(
            f"\n[PARALLEL] Starting {symbol} at {datetime.now().strftime('%H:%M:%S')}"
        )

        result = run_strategy_comparison(
            symbol=symbol,
            start=start,
            end=end,
            cash=cash,
            commission=commission,
            slippage=slippage,
            show_plots=False,  # Force off in parallel mode
            strategies_with_timeframes=strategies_with_timeframes,
        )

        duration = time.time() - symbol_start
        print(f"\n[PARALLEL] ✓ Completed {symbol} in {duration:.1f}s")
        return result

    except Exception as e:
        duration = time.time() - symbol_start
        print(f"\n[PARALLEL] ✗ FAILED {symbol} after {duration:.1f}s")
        print(f"  Error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None


def prefetch_data_for_symbols(symbols: list[str], start, end, refresh_cache: bool = False) -> None:
    """
    Pre-fetch all data for symbols to populate cache and avoid concurrent writes.

    Args:
        symbols: List of ticker symbols
        start: Start datetime
        end: End datetime
        refresh_cache: If True, force refresh from API bypassing cache
    """
    from data.alpaca_data import fetch_daily_bars, fetch_minute_bars

    print(f"\n{'='*70}")
    print(f"PRE-FETCHING DATA FOR {len(symbols)} SYMBOLS")
    if refresh_cache:
        print(f"CACHE REFRESH MODE: Forcing API fetch")
    print(f"{'='*70}")
    print(f"Start: {start}")
    print(f"End: {end}")
    print(f"Symbols: {', '.join(symbols)}\n")

    overall_start = time.time()

    for i, symbol in enumerate(symbols, 1):
        symbol_start = time.time()
        print(f"[{i}/{len(symbols)}] Pre-fetching {symbol}...")

        # Fetch daily data
        try:
            daily_start = time.time()
            fetch_daily_bars(symbol, start, end, refresh_cache=refresh_cache)
            daily_duration = time.time() - daily_start
            print(f"  ✓ Daily data fetched ({daily_duration:.1f}s)")
        except Exception as e:
            print(f"  ✗ Daily data FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()

        # Fetch minute data
        try:
            minute_start = time.time()
            fetch_minute_bars(symbol, start, end, refresh_cache=refresh_cache)
            minute_duration = time.time() - minute_start
            print(f"  ✓ Minute data fetched ({minute_duration:.1f}s)")
        except Exception as e:
            print(f"  ✗ Minute data FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()

        symbol_duration = time.time() - symbol_start
        print(f"  Total: {symbol_duration:.1f}s\n")

    overall_duration = time.time() - overall_start
    print(f"{'='*70}")
    print(f"PRE-FETCH COMPLETE: {overall_duration:.1f}s total")
    print(f"{'='*70}\n")


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
    # Clean up global_comparison directory before starting
    comparison_dir = "global_comparison"
    if os.path.exists(comparison_dir):
        print(f"Clearing {comparison_dir} directory...")
        shutil.rmtree(comparison_dir)
    os.makedirs(comparison_dir, exist_ok=True)

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
        print("WARNING: --plot flag ignored in multi-asset mode (too many windows)\n")
        show_plots = False

    # Get strategies with their timeframes
    all_strategies = get_strategy_map_with_timeframes()

    # Filter strategies if --strategies flag provided
    if args.strategies is not None:
        # Validate strategy keys
        invalid_keys = [k for k in args.strategies if k not in all_strategies]
        if invalid_keys:
            print(f"ERROR: Invalid strategy keys: {', '.join(invalid_keys)}")
            print(f"Available strategies: {', '.join(all_strategies.keys())}")
            return

        # Filter to only requested strategies
        strategies_with_timeframes = {
            k: v for k, v in all_strategies.items() if k in args.strategies
        }
        print(
            f"\nRunning {len(strategies_with_timeframes)} strategies: {', '.join(strategies_with_timeframes.keys())}\n"
        )
    else:
        strategies_with_timeframes = all_strategies

    # Determine execution mode
    use_parallel = args.parallel and len(symbols) > 1

    if use_parallel:
        print(f"\n🚀 PARALLEL MODE: Using up to {os.cpu_count()} workers\n")

        # Pre-fetch all data to avoid cache conflicts
        prefetch_data_for_symbols(symbols, start, end, refresh_cache=args.refresh_cache)

        # Execute in parallel
        all_results = []
        max_workers = min(len(symbols), os.cpu_count() or 4)
        overall_start = time.time()

        print(f"\n{'='*70}")
        print(f"STARTING PARALLEL EXECUTION WITH {max_workers} WORKERS")
        print(f"{'='*70}\n")

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs using module-level function
            future_to_symbol = {
                executor.submit(
                    _run_single_symbol_backtest,
                    symbol,
                    start,
                    end,
                    args.cash,
                    args.commission,
                    args.slippage,
                    strategies_with_timeframes,
                ): symbol
                for symbol in symbols
            }

            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                completed += 1

                try:
                    result = future.result()
                    if result is not None:
                        all_results.append(result)
                    print(f"\n[PROGRESS] {completed}/{len(symbols)} symbols completed")
                except Exception as e:
                    print(f"\n[ERROR] Failed to retrieve result for {symbol}: {e}")
                    traceback.print_exc()

        overall_duration = time.time() - overall_start
        print(f"\n{'='*70}")
        print(f"PARALLEL EXECUTION COMPLETE")
        print(f"Total time: {overall_duration:.1f}s")
        print(f"Average: {overall_duration/len(symbols):.1f}s per symbol")
        print(
            f"Speedup: ~{(len(symbols)*60)/overall_duration:.1f}x vs sequential (estimated)"
        )
        print(f"{'='*70}\n")

    else:
        # Sequential execution (original code)
        if not use_parallel and len(symbols) > 1:
            print(f"\n📝 SEQUENTIAL MODE (use --parallel for faster execution)\n")

        all_results = []
        for i, symbol in enumerate(symbols, 1):
            print(f"\n[{i}/{len(symbols)}] Processing {symbol}...")
            symbol_start = time.time()

            try:
                result = run_strategy_comparison(
                    symbol=symbol,
                    start=start,
                    end=end,
                    cash=args.cash,
                    commission=args.commission,
                    slippage=args.slippage,
                    show_plots=show_plots,
                    strategies_with_timeframes=strategies_with_timeframes,
                    refresh_cache=args.refresh_cache,
                )
                all_results.append(result)

                duration = time.time() - symbol_start
                print(f"✓ Completed {symbol} in {duration:.1f}s")

            except Exception as e:
                duration = time.time() - symbol_start
                print(f"✗ FAILED {symbol} after {duration:.1f}s")
                print(f"  Error: {type(e).__name__}: {e}")
                traceback.print_exc()

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
    from data.volatility_export import (
        export_volatility_to_csv,
        print_volatility_summary_table,
    )

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
