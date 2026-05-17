"""
Main entry point for the backtesting CLI.

Routes commands to appropriate handlers in the commands module.
"""

from commands import (
    build_parser,
    get_strategy_class,
    get_strategy_map,
    handle_single_command,
    handle_compare_single_command,
    handle_compare_multi_command,
    handle_analyze_volatility_command,
    DEFAULT_ASSETS,
)
from config import parse_date


def main():
    # Build parser and parse arguments
    parser = build_parser()
    args = parser.parse_args()

    # Parse dates
    start = parse_date(args.start)
    end = parse_date(args.end)

    if start >= end:
        raise ValueError("Start date must be earlier than end date.")

    # Route to appropriate command handler
    if args.command == "single":
        strategy_cls = get_strategy_class(args.strategy)
        handle_single_command(args, strategy_cls, start, end)

    elif args.command == "compare-single":
        strategies = get_strategy_map()
        handle_compare_single_command(args, strategies, start, end)

    elif args.command == "compare-multi":
        strategies = get_strategy_map()
        handle_compare_multi_command(args, strategies, start, end, DEFAULT_ASSETS)

    elif args.command == "analyze-volatility":
        handle_analyze_volatility_command(args, start, end, DEFAULT_ASSETS)


if __name__ == "__main__":
    main()
