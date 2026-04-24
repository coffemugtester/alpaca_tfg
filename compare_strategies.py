#!/usr/bin/env python3
"""
CLI tool for comparing DCA baseline vs DipBuyer test strategy.

Usage:
    python compare_strategies.py --symbol SPY --start 2016-01-04 --end 2026-01-02
"""

import argparse
from config import parse_date, CASH_DEFAULT, COMMISSION_DEFAULT, SLIPPAGE_DEFAULT
from backtesting.strategy_comparison import run_strategy_comparison


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare DCA baseline vs DipBuyer test strategy"
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
        default="2016-01-04",
        help="Start date in YYYY-MM-DD format (default: 2016-01-04)",
    )

    parser.add_argument(
        "--end",
        type=str,
        default="2026-01-02",
        help="End date in YYYY-MM-DD format (default: 2026-01-02)",
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


def main():
    args = parse_args()

    # Parse dates
    start = parse_date(args.start)
    end = parse_date(args.end)

    if start >= end:
        raise ValueError("Start date must be earlier than end date.")

    # Run comparison
    run_strategy_comparison(
        symbol=args.symbol,
        start=start,
        end=end,
        cash=args.cash,
        commission=args.commission,
        slippage=args.slippage,
    )


if __name__ == "__main__":
    main()
