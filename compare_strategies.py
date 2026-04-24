#!/usr/bin/env python3
"""
CLI tool for comparing DCA baseline vs dinamica test strategy.

Usage:
    python compare_strategies.py --symbol SPY --start 2016-01-04 --end 2026-01-02
"""

import argparse
from config import parse_date, CASH_DEFAULT, COMMISSION_DEFAULT, SLIPPAGE_DEFAULT
from backtesting.strategy_comparison import run_strategy_comparison, print_summary_table

# Default assets to compare if --symbol not specified
DEFAULT_ASSETS = ["SPY", "QQQ", "IWM", "GLD", "TLT", "AAPL", "AMD", "XLE"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare DCA baseline vs Dinamica test strategy"
    )

    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Ticker symbol to analyze, e.g. SPY, QQQ, AAPL (default: run all 8 default assets)",
    )

    parser.add_argument(
        "--start",
        type=str,
        default="2016-01-01",
        help="Start date in YYYY-MM-DD format (default: 2016-01-01)",
    )

    parser.add_argument(
        "--end",
        type=str,
        default="2026-01-01",
        help="End date in YYYY-MM-DD format (default: 2026-01-01)",
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

    parser.add_argument(
        "--plot",
        action="store_true",
        help="Show matplotlib plots (default: False)",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Parse dates
    start = parse_date(args.start)
    end = parse_date(args.end)

    if start >= end:
        raise ValueError("Start date must be earlier than end date.")

    # Determine which symbols to run
    if args.symbol is None:
        symbols = DEFAULT_ASSETS
        print(f"\nNo --symbol specified. Running comparison for {len(symbols)} default assets:")
        print(f"{', '.join(symbols)}\n")
    else:
        symbols = [args.symbol]

    # Force disable plots in multi-asset mode
    show_plots = args.plot
    if len(symbols) > 1 and args.plot:
        print("WARNING: --plot flag ignored in multi-asset mode (too many windows)\n")
        show_plots = False

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
        )
        all_results.append(result)

    # Print summary table if multiple assets
    if len(symbols) > 1:
        print_summary_table(all_results)


if __name__ == "__main__":
    main()
