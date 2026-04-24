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
from strategies.dinamica import DinamicaStrategy
from strategies.meanreversion import MeanReversionStrategy
from strategies.tacticaltrenddip import TacticalTrendDipStrategy


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
) -> dict:
    """
    Run 3-strategy comparison: DCA, Dinamica, and MeanReversion.

    Args:
        symbol: Ticker to backtest
        start: Start date
        end: End date
        cash: Initial cash
        commission: Commission rate (default 0.02%)
        slippage: Slippage rate (default 0.03%)
        show_plots: Whether to display matplotlib plots (default False)

    Returns:
        Dict with symbol and strategy results
    """
    print("\n" + "=" * 80)
    print(f"STRATEGY COMPARISON: DCA | Dinamica | MeanReversion | TacticalTrendDip")
    print(f"Symbol: {symbol} | Period: {start.date()} to {end.date()}")
    print("=" * 80 + "\n")

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

    # Run DCA baseline
    print("Running DCA...")
    dca_result = _run_single_strategy(
        strategy_cls=DollarCostAveraging,
        data_feed=data_feed,
        symbol=symbol,
        cash=cash,
        commission=commission,
        slippage=slippage,
        monthly_invest=monthly_invest,
        num_months=num_months,
        show_plots=show_plots,
    )

    # Run Dinamica
    print("Running Dinamica...")
    dinamica_result = _run_single_strategy(
        strategy_cls=DinamicaStrategy,
        data_feed=data_feed,
        symbol=symbol,
        cash=cash,
        commission=commission,
        slippage=slippage,
        monthly_invest=monthly_invest,
        num_months=num_months,
        show_plots=show_plots,
    )

    # Run MeanReversion
    print("Running MeanReversion...")
    meanrev_result = _run_single_strategy(
        strategy_cls=MeanReversionStrategy,
        data_feed=data_feed,
        symbol=symbol,
        cash=cash,
        commission=commission,
        slippage=slippage,
        monthly_invest=None,
        num_months=num_months,
        show_plots=show_plots,
    )

    # Run TacticalTrendDip
    print("Running TacticalTrendDip...")
    tactical_result = _run_single_strategy(
        strategy_cls=TacticalTrendDipStrategy,
        data_feed=data_feed,
        symbol=symbol,
        cash=cash,
        commission=commission,
        slippage=slippage,
        monthly_invest=None,
        num_months=num_months,
        show_plots=show_plots,
    )

    # Display comparison
    _print_comparison(dca_result, dinamica_result, meanrev_result, tactical_result, cash)

    # Export to CSV
    _export_to_csv(symbol, dca_result, dinamica_result, meanrev_result, tactical_result, cash)

    # Return results for summary table
    return {
        "symbol": symbol,
        "dca": dca_result,
        "dinamica": dinamica_result,
        "meanrev": meanrev_result,
        "tactical": tactical_result,
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
    if strategy_cls == DollarCostAveraging or strategy_cls == DinamicaStrategy:
        cerebro.addstrategy(strategy_cls, monthly_invest=monthly_invest, show_plot=show_plots)
    elif strategy_cls == MeanReversionStrategy:
        cerebro.addstrategy(strategy_cls, total_months=num_months, printlog=False, show_plot=show_plots)
    else:
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


def _print_comparison(dca: dict, dinamica: dict, meanrev: dict, tactical: dict, initial_cash: float) -> None:
    """Print 4-strategy comparison table."""
    print("\n" + "=" * 120)
    print("RESULTS")
    print("=" * 120)

    # Calculate metrics for all strategies
    dca_return = ((dca["final_value"] - initial_cash) / initial_cash) * 100
    dinamica_return = ((dinamica["final_value"] - initial_cash) / initial_cash) * 100
    meanrev_return = ((meanrev["final_value"] - initial_cash) / initial_cash) * 100
    tactical_return = ((tactical["final_value"] - initial_cash) / initial_cash) * 100

    # Print header
    header = f"{'Metric':<20} {'DCA':>15} {'Dinamica':>15} {'MeanReversion':>15} {'TacticalTrendDip':>18}"
    print(header)
    print("-" * 120)

    # Final Value
    print(
        f"{'Final Value':<20} "
        f"${dca['final_value']:>14,.2f} "
        f"${dinamica['final_value']:>14,.2f} "
        f"${meanrev['final_value']:>14,.2f} "
        f"${tactical['final_value']:>17,.2f}"
    )

    # Total Return
    print(
        f"{'Total Return %':<20} "
        f"{dca_return:>14.2f}% "
        f"{dinamica_return:>14.2f}% "
        f"{meanrev_return:>14.2f}% "
        f"{tactical_return:>17.2f}%"
    )

    # Sharpe Ratio
    dca_sharpe_str = f"{dca['sharpe_ratio']:.3f}" if dca["sharpe_ratio"] is not None else "N/A"
    dinamica_sharpe_str = f"{dinamica['sharpe_ratio']:.3f}" if dinamica["sharpe_ratio"] is not None else "N/A"
    meanrev_sharpe_str = f"{meanrev['sharpe_ratio']:.3f}" if meanrev["sharpe_ratio"] is not None else "N/A"
    tactical_sharpe_str = f"{tactical['sharpe_ratio']:.3f}" if tactical["sharpe_ratio"] is not None else "N/A"
    print(
        f"{'Sharpe Ratio':<20} "
        f"{dca_sharpe_str:>15} "
        f"{dinamica_sharpe_str:>15} "
        f"{meanrev_sharpe_str:>15} "
        f"{tactical_sharpe_str:>18}"
    )

    # Max Drawdown
    dca_dd = dca["max_drawdown"] if dca["max_drawdown"] is not None else 0.0
    dinamica_dd = dinamica["max_drawdown"] if dinamica["max_drawdown"] is not None else 0.0
    meanrev_dd = meanrev["max_drawdown"] if meanrev["max_drawdown"] is not None else 0.0
    tactical_dd = tactical["max_drawdown"] if tactical["max_drawdown"] is not None else 0.0
    print(
        f"{'Max Drawdown':<20} "
        f"{dca_dd*100:>14.2f}% "
        f"{dinamica_dd*100:>14.2f}% "
        f"{meanrev_dd*100:>14.2f}% "
        f"{tactical_dd*100:>17.2f}%"
    )

    # Unused Cash
    print(
        f"{'Unused Cash':<20} "
        f"${dca['final_cash']:>14,.2f} "
        f"${dinamica['final_cash']:>14,.2f} "
        f"${meanrev['final_cash']:>14,.2f} "
        f"${tactical['final_cash']:>17,.2f}"
    )

    # Order Count
    print(
        f"{'Order Count':<20} "
        f"{dca['order_count']:>15} "
        f"{dinamica['order_count']:>15} "
        f"{meanrev['order_count']:>15} "
        f"{tactical['order_count']:>18}"
    )

    print("=" * 120)
    print("\n")


def _export_to_csv(
    symbol: str,
    dca: dict,
    dinamica: dict,
    meanrev: dict,
    tactical: dict,
    initial_cash: float,
) -> None:
    """Export comparison results to CSV in append mode."""
    # Create directory if it doesn't exist
    csv_dir = Path.cwd() / "global_comparison"
    csv_dir.mkdir(exist_ok=True)

    csv_path = csv_dir / "comparison_results.csv"

    # Check if file exists to determine if we need to write header
    file_exists = csv_path.exists()

    # Prepare rows
    strategies = [
        ("DCA", dca),
        ("Dinamica", dinamica),
        ("MeanReversion", meanrev),
        ("TacticalTrendDip", tactical),
    ]

    rows = []
    for strategy_name, result in strategies:
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

    print(f"Results exported to: {csv_path}")
    print(f"Appended 4 rows (DCA, Dinamica, MeanReversion, TacticalTrendDip)\n")


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
    """
    print("\n" + "=" * 120)
    print("MULTI-ASSET SUMMARY")
    print("=" * 120)

    # Header
    header = f"{'Asset':<8} {'DCA Return':>13} {'Dinamica Return':>16} {'MeanRev Return':>16} {'Tactical Return':>16} {'Best Strategy':>15}"
    print(header)
    print("-" * 120)

    # Rows: one per asset
    for result in all_results:
        symbol = result["symbol"]
        initial_cash = result["initial_cash"]

        # Calculate returns
        dca_return = (
            (result["dca"]["final_value"] - initial_cash) / initial_cash * 100
        )
        dinamica_return = (
            (result["dinamica"]["final_value"] - initial_cash) / initial_cash * 100
        )
        meanrev_return = (
            (result["meanrev"]["final_value"] - initial_cash) / initial_cash * 100
        )
        tactical_return = (
            (result["tactical"]["final_value"] - initial_cash) / initial_cash * 100
        )

        # Determine best strategy
        returns = {
            "DCA": dca_return,
            "Dinamica": dinamica_return,
            "MeanRev": meanrev_return,
            "Tactical": tactical_return,
        }
        best_strategy = max(returns, key=returns.get)

        # Print row
        print(
            f"{symbol:<8} "
            f"{dca_return:>12.2f}% "
            f"{dinamica_return:>15.2f}% "
            f"{meanrev_return:>15.2f}% "
            f"{tactical_return:>15.2f}% "
            f"{best_strategy:>15}"
        )

    print("=" * 120)
    print(f"\nAll results exported to: global_comparison/comparison_results.csv\n")
