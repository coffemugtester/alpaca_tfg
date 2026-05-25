"""
Strategy comparison module for iterative Dinamica improvements.

Compares DCA (baseline) vs Dinamica (test) to measure delta from known-good strategy.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Type

import backtrader as bt

from config import calculate_months_between
from data.alpaca_data import fetch_daily_bars
from backtesting.data_adapter import df_to_bt_feed
from strategies.dca import DollarCostAveraging
from strategies.buy_and_hold import BuyAndHold
from strategies.tacticalmonthly import TacticalMonthlyRedistributed
from strategies.tacticalatrmonthly import TacticalAtrMonthly


# Asset classification with hierarchical type/category structure
ASSET_CLASSIFICATIONS = {
    # ETFs
    "SPY": ("ETF", "Broad Market"),
    "QQQ": ("ETF", "Tech"),
    "IWM": ("ETF", "Small Cap"),
    "XLE": ("ETF", "Energy"),
    "GLD": ("ETF", "Gold"),
    "TLT": ("ETF", "Treasury Bond"),

    # Individual Stocks - Tech
    "AAPL": ("Stock", "Tech"),
    "AMD": ("Stock", "Tech"),

    # Individual Stocks - Travel & Leisure
    "BKNG": ("Stock", "Travel"),
    "EXPE": ("Stock", "Travel"),
    "RCL": ("Stock", "Cruise"),
    "CCL": ("Stock", "Cruise"),
    "NCLH": ("Stock", "Cruise"),
    "TRIP": ("Stock", "Travel"),
    "MMYT": ("Stock", "Travel"),
    "TNL": ("Stock", "Travel"),

    # Individual Stocks - Other
    "LIND": ("Stock", "Industrial"),
}


def get_asset_classification(symbol: str) -> tuple[str, str]:
    """
    Get the type and category for a given asset symbol.

    Args:
        symbol: Asset ticker symbol

    Returns:
        Tuple of (type, category). Defaults to ("Other", "Unknown") if not found.

    Example:
        >>> get_asset_classification("SPY")
        ("ETF", "Broad Market")
        >>> get_asset_classification("AAPL")
        ("Stock", "Tech")
    """
    return ASSET_CLASSIFICATIONS.get(symbol, ("Other", "Unknown"))


class OrderCountAnalyzer(bt.Analyzer):
    """Track all order attempts (submitted, completed, rejected)."""

    def start(self) -> None:
        self.order_count = 0

    def notify_order(self, order):
        """Called for every order state change."""
        # Count all order attempts (submitted, accepted, completed, rejected, etc.)
        # We count on submission to capture all attempts
        if order.status in [order.Submitted]:
            self.order_count += 1

    def get_analysis(self) -> dict:
        return {"order_count": self.order_count}


def run_strategy_comparison(
    symbol: str,
    start: datetime,
    end: datetime,
    cash: float = 10000.0,
    commission: float = 0.0002,
    slippage: float = 0.0003,
    show_plots: bool = False,
    strategies: dict[str, Type[bt.Strategy]] | None = None,
    strategies_with_timeframes: dict[str, tuple[Type[bt.Strategy], str]] | None = None,
    refresh_cache: bool = False,
) -> dict:
    """
    Run multi-strategy comparison on a single asset.

    Args:
        symbol: Ticker to backtest
        start: Start date
        end: End date
        cash: Initial cash
        commission: Commission rate (default 0.02%)
        slippage: Slippage rate (default 0.03%)
        show_plots: Whether to display matplotlib plots (default False)
        strategies: Dict mapping display names to strategy classes (DEPRECATED - use strategies_with_timeframes)
        strategies_with_timeframes: Dict mapping display names to (strategy_class, timeframe) tuples
        refresh_cache: If True, force refresh from API bypassing cache

    Returns:
        Dict with symbol and strategy results
    """
    # Handle backwards compatibility
    if strategies is not None and strategies_with_timeframes is None:
        # Legacy mode: assume all strategies use daily data
        strategies_with_timeframes = {
            name: (strategy_cls, "daily")
            for name, strategy_cls in strategies.items()
        }
    elif strategies_with_timeframes is None:
        # Fallback to hardcoded 4 strategies for backwards compatibility
        strategies_with_timeframes = {
            "DCA": (DollarCostAveraging, "daily"),
            "Buy & Hold": (BuyAndHold, "daily"),
            "TacticalMonthly": (TacticalMonthlyRedistributed, "daily"),
            "TacticalATRMonthly": (TacticalAtrMonthly, "daily"),
        }

    strategy_names = " | ".join(strategies_with_timeframes.keys())
    print("\n" + "=" * 120)
    print(f"STRATEGY COMPARISON: {strategy_names}")
    print(f"Symbol: {symbol} | Period: {start.date()} to {end.date()}")
    print("=" * 120 + "\n")

    # Calculate monthly invest amount
    num_months = calculate_months_between(start, end)
    monthly_invest = cash / num_months

    # Run all strategies
    results = {}
    for strategy_name, (strategy_cls, timeframe) in strategies_with_timeframes.items():
        print(f"Running {strategy_name} ({timeframe} data)...")

        # Fetch data for this strategy's timeframe
        daily_feed = None
        if timeframe == "minute":
            from data.alpaca_data import fetch_minute_bars
            print(f"Fetching minute data...")
            minute_df = fetch_minute_bars(symbol=symbol, start=start, end=end, refresh_cache=refresh_cache)

            if minute_df is None or len(minute_df) == 0:
                print(f"ERROR: No minute data available for {strategy_name}")
                results[strategy_name] = {
                    "final_value": cash,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "final_cash": cash,
                    "order_count": 0,
                }
                continue

            print(f"Loaded {len(minute_df)} minute bars")
            data_feed = df_to_bt_feed(minute_df)

            # Also fetch daily data for trend filter
            print(f"Fetching daily data (trend filter)...")
            daily_df = fetch_daily_bars(symbol=symbol, start=start, end=end, refresh_cache=refresh_cache)
            if daily_df is not None and len(daily_df) > 0:
                daily_feed = df_to_bt_feed(daily_df)
                print(f"Loaded {len(daily_df)} daily bars for trend filter")
        else:
            print(f"Fetching daily data...")
            df = fetch_daily_bars(symbol=symbol, start=start, end=end, refresh_cache=refresh_cache)

            if df is None or len(df) == 0:
                print(f"ERROR: No daily data available for {strategy_name}")
                results[strategy_name] = {
                    "final_value": cash,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "final_cash": cash,
                    "order_count": 0,
                }
                continue

            print(f"Loaded {len(df)} daily bars")
            data_feed = df_to_bt_feed(df)

        # Determine strategy-specific parameters
        if strategy_cls == DollarCostAveraging:
            monthly_invest_param = monthly_invest
        else:
            # BuyAndHold, TacticalMonthly, TacticalATRMonthly, IntradayVolatilityBands don't use monthly_invest
            monthly_invest_param = None

        result = _run_single_strategy(
            strategy_cls=strategy_cls,
            data_feed=data_feed,
            daily_feed=daily_feed,
            symbol=symbol,
            cash=cash,
            commission=commission,
            slippage=slippage,
            monthly_invest=monthly_invest_param,
            num_months=num_months,
            show_plots=show_plots,
        )
        results[strategy_name] = result

    # Display comparison
    _print_comparison(results, cash)

    # Export strategy comparison to CSV
    _export_to_csv(symbol, results, cash, start, end)

    # Export unified trade analytics to CSV
    _export_trades_csv(symbol, results, strategies_with_timeframes)

    # Return results for summary table
    return {
        "symbol": symbol,
        "results": results,
        "initial_cash": cash,
    }


def _run_single_strategy(
    strategy_cls: Type[bt.Strategy],
    data_feed: bt.feeds.PandasData,
    daily_feed: bt.feeds.PandasData | None,
    symbol: str,
    cash: float,
    commission: float,
    slippage: float,
    monthly_invest: float | None,
    num_months: int,
    show_plots: bool,
) -> dict:
    """Run a single strategy and return metrics."""
    cerebro = bt.Cerebro(cheat_on_open=True)
    cerebro.adddata(data_feed, name=symbol)  # Primary feed (datas[0])

    # Add daily feed if provided (for trend filter in minute strategies)
    if daily_feed is not None:
        cerebro.adddata(daily_feed, name=f"{symbol}_daily")  # datas[1]

    # Add strategy with appropriate parameters
    if strategy_cls == DollarCostAveraging:
        cerebro.addstrategy(
            strategy_cls, monthly_invest=monthly_invest, show_plot=show_plots
        )
    else:
        # BuyAndHold, TacticalMonthly, TacticalATRMonthly
        cerebro.addstrategy(strategy_cls, show_plot=show_plots)

    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)
    cerebro.broker.set_slippage_perc(slippage)

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")
    cerebro.addanalyzer(OrderCountAnalyzer, _name="ordercount")

    # Run
    cerebro.run()

    final_value = float(cerebro.broker.getvalue())
    final_cash = float(cerebro.broker.getcash())

    strats = cerebro.runstrats
    trades_data = []
    if strats and len(strats) > 0:
        strat = strats[0][0]
        sharpe_analysis = strat.analyzers.sharpe.get_analysis()
        dd_analysis = strat.analyzers.drawdown.get_analysis()
        order_analysis = strat.analyzers.ordercount.get_analysis()

        sharpe_ratio = sharpe_analysis.get("sharperatio", None)
        max_dd = dd_analysis.get("max", {}).get("drawdown", None)
        if max_dd is not None:
            max_dd = max_dd / 100.0  # Convert to decimal
        order_count = order_analysis.get("order_count", 0)

        # Collect trade data from strategy if it has the mixin
        if hasattr(strat, 'get_all_trades'):
            trades_data = strat.get_all_trades()
    else:
        sharpe_ratio = None
        max_dd = None
        order_count = 0

    return {
        "final_value": final_value,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_dd,
        "final_cash": final_cash,
        "order_count": order_count,
        "trades": trades_data,
    }


def _print_comparison(results: dict, initial_cash: float) -> None:
    """Print multi-strategy comparison table.

    Args:
        results: Dict mapping strategy names to result dicts
        initial_cash: Initial cash amount
    """
    print("\n" + "=" * 140)
    print("RESULTS")
    print("=" * 140)

    # Calculate column width based on number of strategies
    strategy_names = list(results.keys())
    col_width = 15

    # Print header
    header = f"{'Metric':<20} " + " ".join(
        [f"{name:>{col_width}}" for name in strategy_names]
    )
    print(header)
    print("-" * 140)

    # Final Value
    final_values = [
        f"${results[name]['final_value']:>{col_width-1},.2f}" for name in strategy_names
    ]
    print(f"{'Final Value':<20} " + " ".join(final_values))

    # Total Return
    returns = [
        ((results[name]["final_value"] - initial_cash) / initial_cash) * 100
        for name in strategy_names
    ]
    return_strs = [f"{ret:>{col_width-1}.2f}%" for ret in returns]
    print(f"{'Total Return %':<20} " + " ".join(return_strs))

    # Sharpe Ratio
    sharpe_strs = []
    for name in strategy_names:
        sharpe = results[name]["sharpe_ratio"]
        if sharpe is not None:
            sharpe_strs.append(f"{sharpe:>{col_width}.3f}")
        else:
            sharpe_strs.append(f"{'N/A':>{col_width}}")
    print(f"{'Sharpe Ratio':<20} " + " ".join(sharpe_strs))

    # Max Drawdown
    dd_strs = []
    for name in strategy_names:
        dd = results[name]["max_drawdown"]
        if dd is not None:
            dd_strs.append(f"{dd*100:>{col_width-1}.2f}%")
        else:
            dd_strs.append(f"{0.0:>{col_width-1}.2f}%")
    print(f"{'Max Drawdown':<20} " + " ".join(dd_strs))

    # Unused Cash
    cash_strs = [
        f"${results[name]['final_cash']:>{col_width-1},.2f}" for name in strategy_names
    ]
    print(f"{'Unused Cash':<20} " + " ".join(cash_strs))

    # Order Count
    order_strs = [
        f"{results[name]['order_count']:>{col_width}}" for name in strategy_names
    ]
    print(f"{'Order Count':<20} " + " ".join(order_strs))

    print("=" * 140)
    print("\n")


def _calculate_cagr(initial_value: float, final_value: float, start: datetime, end: datetime) -> float:
    """
    Calculate Compound Annual Growth Rate (CAGR).

    Formula: ((final_value / initial_value) ^ (1 / years)) - 1

    Args:
        initial_value: Starting portfolio value
        final_value: Ending portfolio value
        start: Start date
        end: End date

    Returns:
        CAGR as a decimal (e.g., 0.15 for 15%)
    """
    if initial_value <= 0 or final_value <= 0:
        return 0.0

    # Calculate years (including fractional years)
    days = (end - start).days
    years = days / 365.25  # Account for leap years

    if years <= 0:
        return 0.0

    cagr = (final_value / initial_value) ** (1 / years) - 1
    return cagr


def _calculate_calmar(cagr: float, max_drawdown: float) -> float:
    """
    Calculate Calmar Ratio.

    Formula: CAGR / abs(Max Drawdown)

    Args:
        cagr: Compound annual growth rate as decimal
        max_drawdown: Maximum drawdown as decimal (positive value)

    Returns:
        Calmar ratio (higher is better)
    """
    if max_drawdown == 0:
        return 0.0

    return cagr / abs(max_drawdown)


def _export_to_csv(
    symbol: str,
    results: dict,
    initial_cash: float,
    start: datetime,
    end: datetime,
) -> None:
    """Export comparison results to CSV in append mode with delta columns vs baselines.

    Args:
        symbol: Asset symbol
        results: Dict mapping strategy names to result dicts
        initial_cash: Initial cash amount
        start: Start date for CAGR calculation
        end: End date for CAGR calculation
    """
    # Create directory if it doesn't exist
    csv_dir = Path.cwd() / "global_comparison"
    csv_dir.mkdir(exist_ok=True)

    csv_path = csv_dir / "comparison_results.csv"

    # Check if file exists to determine if we need to write header
    file_exists = csv_path.exists()

    # Extract baseline metrics (Buy & Hold and DCA)
    baseline_metrics = {}
    for baseline_name in ["Buy & Hold", "DCA"]:
        if baseline_name in results:
            result = results[baseline_name]
            total_return_pct = (
                (result["final_value"] - initial_cash) / initial_cash * 100
                if result["final_value"] > 0
                else 0.0
            )
            max_dd_pct = (
                result["max_drawdown"] * 100
                if result["max_drawdown"] is not None
                else 0.0
            )
            sharpe = (
                result["sharpe_ratio"] if result["sharpe_ratio"] is not None else 0.0
            )
            cagr = _calculate_cagr(initial_cash, result["final_value"], start, end)

            calmar = _calculate_calmar(cagr, result["max_drawdown"] if result["max_drawdown"] else 0.0)

            baseline_metrics[baseline_name] = {
                "final_value": result["final_value"],
                "total_return_pct": total_return_pct,
                "cagr": cagr,
                "sharpe_ratio": sharpe,
                "max_drawdown_pct": max_dd_pct,
                "calmar_ratio": calmar,
                "unused_cash": result["final_cash"],
                "order_count": result["order_count"],
            }

    # Prepare rows with deltas
    rows = []
    for strategy_name, result in results.items():
        total_return_pct = (
            (result["final_value"] - initial_cash) / initial_cash * 100
            if result["final_value"] > 0
            else 0.0
        )
        max_dd_pct = (
            result["max_drawdown"] * 100 if result["max_drawdown"] is not None else 0.0
        )
        sharpe = result["sharpe_ratio"] if result["sharpe_ratio"] is not None else 0.0
        cagr = _calculate_cagr(initial_cash, result["final_value"], start, end)
        calmar = _calculate_calmar(cagr, result["max_drawdown"] if result["max_drawdown"] else 0.0)

        # Calculate deltas vs Buy & Hold
        if "Buy & Hold" in baseline_metrics:
            bnh = baseline_metrics["Buy & Hold"]
            final_value_vs_bnh = (
                result["final_value"] - bnh["final_value"]
                if strategy_name != "Buy & Hold"
                else 0.0
            )
            total_return_vs_bnh = (
                total_return_pct - bnh["total_return_pct"]
                if strategy_name != "Buy & Hold"
                else 0.0
            )
            cagr_vs_bnh = (
                cagr - bnh["cagr"] if strategy_name != "Buy & Hold" else 0.0
            )
            sharpe_vs_bnh = (
                sharpe - bnh["sharpe_ratio"] if strategy_name != "Buy & Hold" else 0.0
            )
            max_dd_vs_bnh = (
                max_dd_pct - bnh["max_drawdown_pct"]
                if strategy_name != "Buy & Hold"
                else 0.0
            )
            calmar_vs_bnh = (
                calmar - bnh["calmar_ratio"] if strategy_name != "Buy & Hold" else 0.0
            )
            unused_cash_vs_bnh = (
                result["final_cash"] - bnh["unused_cash"]
                if strategy_name != "Buy & Hold"
                else 0.0
            )
            order_count_vs_bnh = (
                result["order_count"] - bnh["order_count"]
                if strategy_name != "Buy & Hold"
                else 0
            )
        else:
            final_value_vs_bnh = 0.0
            total_return_vs_bnh = 0.0
            cagr_vs_bnh = 0.0
            sharpe_vs_bnh = 0.0
            max_dd_vs_bnh = 0.0
            calmar_vs_bnh = 0.0
            unused_cash_vs_bnh = 0.0
            order_count_vs_bnh = 0

        # Calculate deltas vs DCA
        if "DCA" in baseline_metrics:
            dca = baseline_metrics["DCA"]
            final_value_vs_dca = (
                result["final_value"] - dca["final_value"]
                if strategy_name != "DCA"
                else 0.0
            )
            total_return_vs_dca = (
                total_return_pct - dca["total_return_pct"]
                if strategy_name != "DCA"
                else 0.0
            )
            cagr_vs_dca = (
                cagr - dca["cagr"] if strategy_name != "DCA" else 0.0
            )
            sharpe_vs_dca = (
                sharpe - dca["sharpe_ratio"] if strategy_name != "DCA" else 0.0
            )
            max_dd_vs_dca = (
                max_dd_pct - dca["max_drawdown_pct"] if strategy_name != "DCA" else 0.0
            )
            calmar_vs_dca = (
                calmar - dca["calmar_ratio"] if strategy_name != "DCA" else 0.0
            )
            unused_cash_vs_dca = (
                result["final_cash"] - dca["unused_cash"]
                if strategy_name != "DCA"
                else 0.0
            )
            order_count_vs_dca = (
                result["order_count"] - dca["order_count"]
                if strategy_name != "DCA"
                else 0
            )
        else:
            final_value_vs_dca = 0.0
            total_return_vs_dca = 0.0
            cagr_vs_dca = 0.0
            sharpe_vs_dca = 0.0
            max_dd_vs_dca = 0.0
            calmar_vs_dca = 0.0
            unused_cash_vs_dca = 0.0
            order_count_vs_dca = 0

        asset_type, asset_category = get_asset_classification(symbol)
        rows.append(
            {
                "asset": symbol,
                "type": asset_type,
                "category": asset_category,
                "strategy": strategy_name,
                "final_value": f"{result['final_value']:.2f}",
                "final_value_vs_bnh": f"{final_value_vs_bnh:.2f}",
                "final_value_vs_dca": f"{final_value_vs_dca:.2f}",
                "total_return_pct": f"{total_return_pct:.2f}",
                "total_return_pct_vs_bnh": f"{total_return_vs_bnh:.2f}",
                "total_return_pct_vs_dca": f"{total_return_vs_dca:.2f}",
                "cagr_pct": f"{cagr * 100:.2f}",
                "cagr_pct_vs_bnh": f"{cagr_vs_bnh * 100:.2f}",
                "cagr_pct_vs_dca": f"{cagr_vs_dca * 100:.2f}",
                "sharpe_ratio": f"{sharpe:.3f}",
                "sharpe_ratio_vs_bnh": f"{sharpe_vs_bnh:.3f}",
                "sharpe_ratio_vs_dca": f"{sharpe_vs_dca:.3f}",
                "max_drawdown_pct": f"{max_dd_pct:.2f}",
                "max_drawdown_pct_vs_bnh": f"{max_dd_vs_bnh:.2f}",
                "max_drawdown_pct_vs_dca": f"{max_dd_vs_dca:.2f}",
                "calmar_ratio": f"{calmar:.3f}",
                "calmar_ratio_vs_bnh": f"{calmar_vs_bnh:.3f}",
                "calmar_ratio_vs_dca": f"{calmar_vs_dca:.3f}",
                "unused_cash": f"{result['final_cash']:.2f}",
                "unused_cash_vs_bnh": f"{unused_cash_vs_bnh:.2f}",
                "unused_cash_vs_dca": f"{unused_cash_vs_dca:.2f}",
                "order_count": result["order_count"],
                "order_count_vs_bnh": order_count_vs_bnh,
                "order_count_vs_dca": order_count_vs_dca,
            }
        )

    # Write to CSV in append mode
    with csv_path.open("a", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "asset",
            "type",
            "category",
            "strategy",
            "final_value",
            "final_value_vs_bnh",
            "final_value_vs_dca",
            "total_return_pct",
            "total_return_pct_vs_bnh",
            "total_return_pct_vs_dca",
            "cagr_pct",
            "cagr_pct_vs_bnh",
            "cagr_pct_vs_dca",
            "sharpe_ratio",
            "sharpe_ratio_vs_bnh",
            "sharpe_ratio_vs_dca",
            "max_drawdown_pct",
            "max_drawdown_pct_vs_bnh",
            "max_drawdown_pct_vs_dca",
            "calmar_ratio",
            "calmar_ratio_vs_bnh",
            "calmar_ratio_vs_dca",
            "unused_cash",
            "unused_cash_vs_bnh",
            "unused_cash_vs_dca",
            "order_count",
            "order_count_vs_bnh",
            "order_count_vs_dca",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header if file is new
        if not file_exists:
            writer.writeheader()

        # Write rows
        writer.writerows(rows)

    strategy_list = ", ".join(results.keys())
    print(f"Results exported to: {csv_path}")
    print(f"Appended {len(results)} rows ({strategy_list})\n")


def _format_delta_value(delta: float) -> str:
    """Format dollar delta with color indicator."""
    if delta > 0:
        return f"+${delta:,.2f}"
    elif delta < 0:
        return f"-${abs(delta):,.2f}"
    else:
        return "$0.00"


def _format_delta_pct(delta: float) -> str:
    """Format percentage delta."""
    if delta > 0:
        return f"+{delta:.2f}%"
    elif delta < 0:
        return f"{delta:.2f}%"
    else:
        return "0.00%"


def _format_delta_sharpe(delta: float) -> str:
    """Format Sharpe delta."""
    if delta > 0:
        return f"+{delta:.3f}"
    elif delta < 0:
        return f"{delta:.3f}"
    else:
        return "0.000"


def _format_delta_dd(delta: float) -> str:
    """Format drawdown delta (negative is better)."""
    if delta < 0:
        return f"{delta*100:.2f}%"
    elif delta > 0:
        return f"+{delta*100:.2f}%"
    else:
        return "0.00%"


def print_summary_table(all_results: list[dict]) -> None:
    """
    Print summary table for multi-asset comparison.

    Shows total return % for each asset × strategy combination, with delta
    columns comparing tactical strategies to Buy & Hold and DCA baselines.

    Args:
        all_results: List of result dicts from run_strategy_comparison()
    """
    if not all_results:
        return

    # Extract strategy names from first result
    first_result = all_results[0]
    strategy_names = list(first_result["results"].keys())

    # Identify baseline and tactical strategies
    baseline_names = ["DCA", "Buy & Hold"]
    tactical_names = [name for name in strategy_names if name not in baseline_names]

    col_width = 12
    delta_width = 10

    print("\n" + "=" * 200)
    print("MULTI-ASSET SUMMARY (with deltas vs baselines)")
    print("=" * 200)

    # Build header
    header_parts = [f"{'Asset':<8}", f"{'Type':<8}", f"{'Category':<15}"]

    # Baseline strategy columns
    for name in baseline_names:
        if name in strategy_names:
            header_parts.append(f"{name:>{col_width}}")

    # Tactical strategy columns with deltas
    for name in tactical_names:
        header_parts.append(f"{name:>{col_width}}")
        header_parts.append(f"{'vs BnH':>{delta_width}}")
        header_parts.append(f"{'vs DCA':>{delta_width}}")

    header_parts.append(f"{'Best':>15}")
    header = " ".join(header_parts)
    print(header)
    print("-" * 200)

    # Rows: one per asset
    for result in all_results:
        symbol = result["symbol"]
        asset_type, asset_category = get_asset_classification(symbol)
        initial_cash = result["initial_cash"]
        strategy_results = result["results"]

        # Calculate returns for all strategies
        returns = {}
        for name in strategy_names:
            final_value = strategy_results[name]["final_value"]
            ret = ((final_value - initial_cash) / initial_cash) * 100
            returns[name] = ret

        # Get baseline returns
        bnh_return = returns.get("Buy & Hold", 0.0)
        dca_return = returns.get("DCA", 0.0)

        # Determine best strategy
        best_strategy = max(returns, key=lambda x: returns[x])

        # Build row
        row_parts = [f"{symbol:<8}", f"{asset_type:<8}", f"{asset_category:<15}"]

        # Baseline returns
        for name in baseline_names:
            if name in strategy_names:
                row_parts.append(f"{returns[name]:>{col_width-1}.2f}%")

        # Tactical returns with deltas
        for name in tactical_names:
            ret = returns[name]
            delta_bnh = ret - bnh_return
            delta_dca = ret - dca_return

            row_parts.append(f"{ret:>{col_width-1}.2f}%")
            row_parts.append(f"{_format_delta(delta_bnh):>{delta_width}}")
            row_parts.append(f"{_format_delta(delta_dca):>{delta_width}}")

        row_parts.append(f"{best_strategy:>15}")
        print(" ".join(row_parts))

    print("=" * 200)
    print("\nAll results exported to: global_comparison/comparison_results.csv\n")


def _format_delta(delta: float) -> str:
    """Format delta percentage with +/- sign."""
    if delta > 0:
        return f"+{delta:.1f}%"
    elif delta < 0:
        return f"{delta:.1f}%"
    else:
        return "0.0%"


def _export_trades_csv(
    symbol: str,
    results: dict,
    strategies_with_timeframes: dict[str, tuple[Type[bt.Strategy], str]],
) -> None:
    """
    Export unified trade analytics to CSV for a single symbol.

    Creates/appends to global_comparison/all_trades.csv with all trades from all strategies.

    Args:
        symbol: The asset symbol
        results: Dict mapping strategy names to result dicts (containing 'trades' key)
        strategies_with_timeframes: Dict mapping strategy names to (strategy_class, timeframe) tuples
    """
    output_dir = Path("global_comparison")
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / "all_trades.csv"

    # Determine if we need to write headers (file doesn't exist or is empty)
    write_headers = not csv_path.exists() or csv_path.stat().st_size == 0

    # Collect all trades from all strategies for this symbol
    all_trades_data = []

    for strategy_name, result in results.items():
        trades = result.get("trades", [])

        if not trades:
            # No trades for this strategy - skip
            continue

        # Add strategy and symbol info to each trade
        for trade in trades:
            trade_row = {
                "symbol": symbol,
                "strategy": strategy_name,
                "direction": trade["direction"],
                "entry_time": trade["entry_time"].strftime("%Y-%m-%d %H:%M:%S") if trade["entry_time"] else "",
                "exit_time": trade["exit_time"].strftime("%Y-%m-%d %H:%M:%S") if trade["exit_time"] else "",
                "entry_price": f"{trade['entry_price']:.2f}",
                "exit_price": f"{trade['exit_price']:.2f}" if trade["exit_price"] is not None else "",
                "position_size": f"{trade['position_size']:.2f}",
                "cash_deployed": f"{trade['cash_deployed']:.2f}",
                "cumulative_shares": f"{trade['cumulative_shares']:.2f}",
                "cumulative_exposure": f"{trade['cumulative_exposure']:.2f}",
                "remaining_cash": f"{trade['remaining_cash']:.2f}",
                "total_portfolio_value": f"{trade['total_portfolio_value']:.2f}",
                "pnl_dollars": f"{trade['pnl_dollars']:.2f}" if trade["pnl_dollars"] is not None else "",
                "pnl_pct": f"{trade['pnl_pct']:.4f}" if trade["pnl_pct"] is not None else "",
                "trade_status": trade["trade_status"],
                "exit_reason": trade["exit_reason"] if trade["exit_reason"] else "",
                "hold_duration_days": f"{trade['hold_duration_seconds'] / 86400:.2f}" if trade["hold_duration_seconds"] is not None else "",
                "stop_price": f"{trade['stop_price']:.2f}" if trade["stop_price"] is not None else "",
            }
            all_trades_data.append(trade_row)

    if not all_trades_data:
        # No trades to export for this symbol
        return

    # Write/append to CSV
    fieldnames = [
        "symbol",
        "strategy",
        "direction",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "position_size",
        "cash_deployed",
        "cumulative_shares",
        "cumulative_exposure",
        "remaining_cash",
        "total_portfolio_value",
        "pnl_dollars",
        "pnl_pct",
        "trade_status",
        "exit_reason",
        "hold_duration_days",
        "stop_price",
    ]

    mode = "w" if write_headers else "a"
    with open(csv_path, mode, newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if write_headers:
            writer.writeheader()

        for row in all_trades_data:
            writer.writerow(row)

    print(f"Exported {len(all_trades_data)} trades for {symbol} to: {csv_path}")
