"""
Chart generation functions for strategy comparison visualization.
"""

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np


def generate_charts(
    symbol: str,
    results: dict,
    initial_cash: float,
    start: datetime,
    end: datetime,
) -> None:
    """
    Generate and save portfolio value and drawdown charts for all strategies.

    Args:
        symbol: Asset symbol
        results: Dict mapping strategy names to result dicts
        initial_cash: Initial cash amount
        start: Start datetime
        end: End datetime
    """
    # Create output directories
    charts_dir = Path("charts")
    charts_dir.mkdir(exist_ok=True)

    drawdown_dir = Path("drawdown_charts")
    drawdown_dir.mkdir(exist_ok=True)

    # Generate portfolio value chart
    _generate_portfolio_chart(symbol, results, initial_cash, start, end, charts_dir)

    # Generate drawdown chart
    _generate_drawdown_chart(symbol, results, start, end, drawdown_dir)


def _generate_portfolio_chart(
    symbol: str,
    results: dict,
    initial_cash: float,
    start: datetime,
    end: datetime,
    output_dir: Path,
) -> None:
    """Generate portfolio value comparison chart with time-series data."""
    fig, ax = plt.subplots(figsize=(14, 8))

    strategy_names = list(results.keys())
    colors = plt.cm.tab10(np.linspace(0, 1, len(strategy_names)))

    for idx, (strategy_name, color) in enumerate(zip(strategy_names, colors)):
        time_series = results[strategy_name].get("time_series", {})

        if not time_series:
            # Fallback to old behavior if no time series data
            final_value = results[strategy_name]["final_value"]
            ax.plot([start, end], [initial_cash, final_value],
                   label=f"{strategy_name}: ${final_value:,.0f}",
                   color=color, linewidth=2, marker='o')
        else:
            # Extract dates and portfolio values
            dates = sorted(time_series.keys())
            portfolio_values = [time_series[dt]["portfolio_value"] for dt in dates]
            final_value = portfolio_values[-1] if portfolio_values else initial_cash

            # Plot time series
            ax.plot(dates, portfolio_values,
                   label=f"{strategy_name}: ${final_value:,.0f}",
                   color=color, linewidth=2)

    ax.axhline(y=initial_cash, color='gray', linestyle='--', alpha=0.5, label='Capital Inicial')

    # Format date axis
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    ax.set_title(f"{symbol} - Comparación Valor del Portafolio", fontsize=16, fontweight='bold')
    ax.set_xlabel("Fecha", fontsize=12)
    ax.set_ylabel("Valor del Portafolio ($)", fontsize=12)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    # Save chart
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"portfolio_{symbol}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_{timestamp}.png"
    filepath = output_dir / filename
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Saved portfolio chart: {filepath}")


def _generate_drawdown_chart(
    symbol: str,
    results: dict,
    start: datetime,
    end: datetime,
    output_dir: Path,
) -> None:
    """Generate drawdown time-series comparison chart."""
    fig, ax = plt.subplots(figsize=(14, 8))

    strategy_names = list(results.keys())
    colors = plt.cm.tab10(np.linspace(0, 1, len(strategy_names)))

    for idx, (strategy_name, color) in enumerate(zip(strategy_names, colors)):
        time_series = results[strategy_name].get("time_series", {})

        if not time_series:
            # Fallback: show max drawdown as horizontal line
            dd = results[strategy_name].get("max_drawdown", 0.0)
            if dd is not None:
                dd_pct = dd * 100
                ax.axhline(y=-dd_pct, color=color, linestyle='--', alpha=0.7,
                          label=f"{strategy_name}: {dd_pct:.1f}%")
        else:
            # Calculate running drawdown from peak
            dates = sorted(time_series.keys())
            portfolio_values = [time_series[dt]["portfolio_value"] for dt in dates]

            # Calculate drawdown at each point
            peak = portfolio_values[0]
            drawdowns = []
            for value in portfolio_values:
                if value > peak:
                    peak = value
                dd = ((peak - value) / peak * 100) if peak > 0 else 0.0
                drawdowns.append(-dd)  # Negative for display (drawdown goes down)

            max_dd = min(drawdowns) if drawdowns else 0.0

            # Plot time series
            ax.plot(dates, drawdowns,
                   label=f"{strategy_name}: {-max_dd:.1f}%",
                   color=color, linewidth=2)

    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5)

    # Format date axis
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    ax.set_title(f"{symbol} - Comparación de Caídas", fontsize=16, fontweight='bold')
    ax.set_xlabel("Fecha", fontsize=12)
    ax.set_ylabel("Caída (%)", fontsize=12)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    # Save chart
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"drawdown_{symbol}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_{timestamp}.png"
    filepath = output_dir / filename
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Saved drawdown chart: {filepath}")
