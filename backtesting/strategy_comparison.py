"""
Strategy comparison module for iterative DipBuyer improvements.

Compares DCA (baseline) vs DipBuyer (test) to measure delta from known-good strategy.
"""

from datetime import datetime
from typing import Type

import backtrader as bt

from config import calculate_months_between
from data.alpaca_data import fetch_daily_bars
from backtesting.data_adapter import df_to_bt_feed
from strategies.dca import DollarCostAveraging
from strategies.dip_buyer import DipBuyerStrategy


def run_strategy_comparison(
    symbol: str,
    start: datetime,
    end: datetime,
    cash: float = 10000.0,
    commission: float = 0.0002,
    slippage: float = 0.0003,
) -> None:
    """
    Run DCA baseline vs DipBuyer test and display performance comparison.

    Args:
        symbol: Ticker to backtest
        start: Start date
        end: End date
        cash: Initial cash
        commission: Commission rate (default 0.02%)
        slippage: Slippage rate (default 0.03%)
    """
    print("\n" + "=" * 80)
    print(f"STRATEGY COMPARISON: DCA (baseline) vs DipBuyer (test)")
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
    print("Running DCA (baseline)...")
    dca_result = _run_single_strategy(
        strategy_cls=DollarCostAveraging,
        data_feed=data_feed,
        symbol=symbol,
        cash=cash,
        commission=commission,
        slippage=slippage,
        monthly_invest=monthly_invest,
    )

    # Run DipBuyer test
    print("Running DipBuyer (test)...")
    dipbuyer_result = _run_single_strategy(
        strategy_cls=DipBuyerStrategy,
        data_feed=data_feed,
        symbol=symbol,
        cash=cash,
        commission=commission,
        slippage=slippage,
        monthly_invest=monthly_invest,
    )

    # Display comparison
    _print_comparison(dca_result, dipbuyer_result, cash)


def _run_single_strategy(
    strategy_cls: Type[bt.Strategy],
    data_feed: bt.feeds.PandasData,
    symbol: str,
    cash: float,
    commission: float,
    slippage: float,
    monthly_invest: float,
) -> dict:
    """Run a single strategy and return metrics."""
    cerebro = bt.Cerebro(cheat_on_open=True)
    cerebro.adddata(data_feed, name=symbol)
    cerebro.addstrategy(strategy_cls, monthly_invest=monthly_invest)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission)
    cerebro.broker.set_slippage_perc(slippage)

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")

    # Run
    cerebro.run()

    final_value = float(cerebro.broker.getvalue())
    strats = cerebro.runstrats
    if strats and len(strats) > 0:
        strat = strats[0][0]
        sharpe_analysis = strat.analyzers.sharpe.get_analysis()
        dd_analysis = strat.analyzers.drawdown.get_analysis()

        sharpe_ratio = sharpe_analysis.get("sharperatio", None)
        max_dd = dd_analysis.get("max", {}).get("drawdown", None)
        if max_dd is not None:
            max_dd = max_dd / 100.0  # Convert to decimal
    else:
        sharpe_ratio = None
        max_dd = None

    return {
        "final_value": final_value,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_dd,
    }


def _print_comparison(dca: dict, dipbuyer: dict, initial_cash: float) -> None:
    """Print side-by-side comparison with deltas."""
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    # Calculate metrics
    dca_return = ((dca["final_value"] - initial_cash) / initial_cash) * 100
    dipbuyer_return = ((dipbuyer["final_value"] - initial_cash) / initial_cash) * 100
    return_delta = dipbuyer_return - dca_return

    dca_sharpe = dca["sharpe_ratio"] if dca["sharpe_ratio"] is not None else 0.0
    dipbuyer_sharpe = (
        dipbuyer["sharpe_ratio"] if dipbuyer["sharpe_ratio"] is not None else 0.0
    )
    sharpe_delta = dipbuyer_sharpe - dca_sharpe

    dca_dd = dca["max_drawdown"] if dca["max_drawdown"] is not None else 0.0
    dipbuyer_dd = (
        dipbuyer["max_drawdown"] if dipbuyer["max_drawdown"] is not None else 0.0
    )
    dd_delta = dipbuyer_dd - dca_dd

    # Print header
    header = f"{'Metric':<20} {'DCA (baseline)':>18} {'DipBuyer (test)':>18} {'Delta':>15}"
    print(header)
    print("-" * 80)

    # Final Value
    print(
        f"{'Final Value':<20} ${dca['final_value']:>17,.2f} ${dipbuyer['final_value']:>17,.2f} "
        f"{_format_delta_value(dipbuyer['final_value'] - dca['final_value']):>15}"
    )

    # Total Return
    print(
        f"{'Total Return %':<20} {dca_return:>17.2f}% {dipbuyer_return:>17.2f}% "
        f"{_format_delta_pct(return_delta):>15}"
    )

    # Sharpe Ratio
    dca_sharpe_str = f"{dca_sharpe:.3f}" if dca["sharpe_ratio"] is not None else "N/A"
    dipbuyer_sharpe_str = (
        f"{dipbuyer_sharpe:.3f}" if dipbuyer["sharpe_ratio"] is not None else "N/A"
    )
    print(
        f"{'Sharpe Ratio':<20} {dca_sharpe_str:>18} {dipbuyer_sharpe_str:>18} "
        f"{_format_delta_sharpe(sharpe_delta):>15}"
    )

    # Max Drawdown
    dca_dd_str = f"{dca_dd*100:.2f}%" if dca["max_drawdown"] is not None else "N/A"
    dipbuyer_dd_str = (
        f"{dipbuyer_dd*100:.2f}%" if dipbuyer["max_drawdown"] is not None else "N/A"
    )
    print(
        f"{'Max Drawdown':<20} {dca_dd_str:>18} {dipbuyer_dd_str:>18} "
        f"{_format_delta_dd(dd_delta):>15}"
    )

    print("=" * 80)

    # Summary verdict
    print("\nVERDICT:")
    if return_delta > 1.0:
        print(f"  ✓ DipBuyer OUTPERFORMS DCA by {return_delta:.2f}%")
    elif return_delta < -1.0:
        print(f"  ✗ DipBuyer UNDERPERFORMS DCA by {abs(return_delta):.2f}%")
    else:
        print(f"  ≈ DipBuyer matches DCA (delta: {return_delta:.2f}%)")

    if sharpe_delta > 0.05:
        print(f"  ✓ Better risk-adjusted returns (Sharpe +{sharpe_delta:.3f})")
    elif sharpe_delta < -0.05:
        print(f"  ✗ Worse risk-adjusted returns (Sharpe {sharpe_delta:.3f})")

    if dd_delta < -0.01:
        print(f"  ✓ Lower drawdown ({dd_delta*100:.2f}%)")
    elif dd_delta > 0.01:
        print(f"  ✗ Higher drawdown (+{dd_delta*100:.2f}%)")

    print("\n")


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
