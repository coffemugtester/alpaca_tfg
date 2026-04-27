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
    strategies: dict = None,
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
        strategies: Dict mapping display names to strategy classes (e.g., {"DCA": DollarCostAveraging})

    Returns:
        Dict with symbol and strategy results
    """
    if strategies is None:
        # Fallback to hardcoded 4 strategies for backwards compatibility
        strategies = {
            "DCA": DollarCostAveraging,
            "Buy & Hold": BuyAndHold,
            "TacticalMonthly": TacticalMonthlyRedistributed,
            "TacticalATRMonthly": TacticalAtrMonthly,
        }

    strategy_names = " | ".join(strategies.keys())
    print("\n" + "=" * 120)
    print(f"STRATEGY COMPARISON: {strategy_names}")
    print(f"Symbol: {symbol} | Period: {start.date()} to {end.date()}")
    print("=" * 120 + "\n")

    # Fetch data once
    print(f"Fetching data...")
    df = fetch_daily_bars(symbol=symbol, start=start, end=end)
    if df is None or len(df) == 0:
        print("ERROR: No data available")
        return
    print(f"Loaded {len(df)} bars\n")

    data_feed = df_to_bt_feed(df)

    # Calculate monthly invest amount
    num_months = calculate_months_between(start, end)
    monthly_invest = cash / num_months

    # Run all strategies
    results = {}
    for strategy_name, strategy_cls in strategies.items():
        print(f"Running {strategy_name}...")

        # Determine strategy-specific parameters
        if strategy_cls == DollarCostAveraging:
            monthly_invest_param = monthly_invest
        else:
            # BuyAndHold, TacticalMonthly, TacticalATRMonthly don't use monthly_invest
            monthly_invest_param = None

        result = _run_single_strategy(
            strategy_cls=strategy_cls,
            data_feed=data_feed,
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

    # Export to CSV
    _export_to_csv(symbol, results, cash)

    # Return results for summary table
    return {
        "symbol": symbol,
        "results": results,
        "initial_cash": cash,
    }


def _run_single_strategy(
    strategy_cls: Type[bt.Strategy],
    data_feed: bt.feeds.PandasData,
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
    cerebro.adddata(data_feed, name=symbol)

    # Add strategy with appropriate parameters
    if strategy_cls == DollarCostAveraging:
        cerebro.addstrategy(strategy_cls, monthly_invest=monthly_invest, show_plot=show_plots)
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
    num_strategies = len(strategy_names)
    col_width = 15

    # Print header
    header = f"{'Metric':<20} " + " ".join([f"{name:>{col_width}}" for name in strategy_names])
    print(header)
    print("-" * 140)

    # Final Value
    final_values = [f"${results[name]['final_value']:>{col_width-1},.2f}" for name in strategy_names]
    print(f"{'Final Value':<20} " + " ".join(final_values))

    # Total Return
    returns = [((results[name]["final_value"] - initial_cash) / initial_cash) * 100 for name in strategy_names]
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
    cash_strs = [f"${results[name]['final_cash']:>{col_width-1},.2f}" for name in strategy_names]
    print(f"{'Unused Cash':<20} " + " ".join(cash_strs))

    # Order Count
    order_strs = [f"{results[name]['order_count']:>{col_width}}" for name in strategy_names]
    print(f"{'Order Count':<20} " + " ".join(order_strs))

    print("=" * 140)
    print("\n")


def _export_to_csv(
    symbol: str,
    results: dict,
    initial_cash: float,
) -> None:
    """Export comparison results to CSV in append mode.

    Args:
        symbol: Asset symbol
        results: Dict mapping strategy names to result dicts
        initial_cash: Initial cash amount
    """
    # Create directory if it doesn't exist
    csv_dir = Path.cwd() / "global_comparison"
    csv_dir.mkdir(exist_ok=True)

    csv_path = csv_dir / "comparison_results.csv"

    # Check if file exists to determine if we need to write header
    file_exists = csv_path.exists()

    # Prepare rows
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

        rows.append(
            {
                "asset": symbol,
                "strategy": strategy_name,
                "final_value": f"{result['final_value']:.2f}",
                "total_return_pct": f"{total_return_pct:.2f}",
                "sharpe_ratio": f"{sharpe:.3f}",
                "max_drawdown_pct": f"{max_dd_pct:.2f}",
                "unused_cash": f"{result['final_cash']:.2f}",
                "order_count": result["order_count"],
            }
        )

    # Write to CSV in append mode
    with csv_path.open("a", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "asset",
            "strategy",
            "final_value",
            "total_return_pct",
            "sharpe_ratio",
            "max_drawdown_pct",
            "unused_cash",
            "order_count",
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

    Shows total return % for each asset × strategy combination.

    Args:
        all_results: List of result dicts from run_strategy_comparison()
    """
    if not all_results:
        return

    # Extract strategy names from first result
    first_result = all_results[0]
    strategy_names = list(first_result["results"].keys())
    col_width = 16

    print("\n" + "=" * 140)
    print("MULTI-ASSET SUMMARY")
    print("=" * 140)

    # Header
    strategy_headers = " ".join([f"{name + ' Return':>{col_width}}" for name in strategy_names])
    header = f"{'Asset':<8} {strategy_headers} {'Best Strategy':>15}"
    print(header)
    print("-" * 140)

    # Rows: one per asset
    for result in all_results:
        symbol = result["symbol"]
        initial_cash = result["initial_cash"]
        strategy_results = result["results"]

        # Calculate returns for all strategies
        returns = {}
        for name in strategy_names:
            final_value = strategy_results[name]["final_value"]
            ret = ((final_value - initial_cash) / initial_cash) * 100
            returns[name] = ret

        # Determine best strategy
        best_strategy = max(returns, key=returns.get)

        # Print row
        return_strs = " ".join([f"{returns[name]:>{col_width-1}.2f}%" for name in strategy_names])
        print(f"{symbol:<8} {return_strs} {best_strategy:>15}")

    print("=" * 140)
    print(f"\nAll results exported to: global_comparison/comparison_results.csv\n")
