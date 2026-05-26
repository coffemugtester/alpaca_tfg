"""
Chart generation functions for strategy comparison visualization.
"""

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
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
    """Generate portfolio value comparison chart."""
    plt.figure(figsize=(14, 8))

    strategy_names = list(results.keys())
    colors = plt.cm.tab10(np.linspace(0, 1, len(strategy_names)))

    for idx, (strategy_name, color) in enumerate(zip(strategy_names, colors)):
        final_value = results[strategy_name]["final_value"]

        # Simple line from initial to final (we don't have time series data here)
        # This is a placeholder - real implementation would need equity curve data
        plt.plot([start, end], [initial_cash, final_value],
                 label=f"{strategy_name}: ${final_value:,.0f}",
                 color=color, linewidth=2, marker='o')

    plt.axhline(y=initial_cash, color='gray', linestyle='--', alpha=0.5, label='Initial Cash')

    plt.title(f"{symbol} - Portfolio Value Comparison", fontsize=16, fontweight='bold')
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Portfolio Value ($)", fontsize=12)
    plt.legend(loc='best', fontsize=10)
    plt.grid(True, alpha=0.3)
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
    """Generate maximum drawdown comparison chart."""
    plt.figure(figsize=(12, 6))

    strategy_names = list(results.keys())
    drawdowns = []

    for strategy_name in strategy_names:
        dd = results[strategy_name].get("max_drawdown", 0.0)
        if dd is not None:
            drawdowns.append(dd * 100)  # Convert to percentage
        else:
            drawdowns.append(0.0)

    # Create bar chart
    colors = plt.cm.RdYlGn_r(np.array(drawdowns) / 100)  # Red for high DD, green for low
    bars = plt.bar(strategy_names, drawdowns, color=colors, edgecolor='black', linewidth=1.5)

    # Add value labels on bars
    for bar, dd in zip(bars, drawdowns):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height,
                f'{dd:.1f}%',
                ha='center', va='bottom', fontsize=10, fontweight='bold')

    plt.title(f"{symbol} - Maximum Drawdown Comparison", fontsize=16, fontweight='bold')
    plt.ylabel("Maximum Drawdown (%)", fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()

    # Save chart
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"drawdown_{symbol}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_{timestamp}.png"
    filepath = output_dir / filename
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"Saved drawdown chart: {filepath}")
