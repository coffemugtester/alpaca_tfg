"""Basic metrics extraction stage for strategy validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np


class BasicMetricsStage:
    """
    Extracts basic performance metrics from backtest results.

    Metrics calculated:
    - CAGR (Compound Annual Growth Rate)
    - Sharpe Ratio
    - Max Drawdown
    - Calmar Ratio (CAGR / Max Drawdown)
    - Win Rate (% of positive return periods)
    - Volatility (annualized standard deviation of returns)
    """

    def run(self, strategy_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """
        Extract metrics from strategy results.

        Args:
            strategy_results: List of dicts with keys:
                - 'strategy_name': str
                - 'cerebro': Backtrader Cerebro instance with analyzers attached
                - 'final_value': float
                - 'start': datetime
                - 'end': datetime
                - 'initial_cash': float

        Returns:
            Dict mapping strategy_name to metrics dict
        """
        metrics_by_strategy = {}

        for result in strategy_results:
            strategy_name = result['strategy_name']
            cerebro = result['cerebro']
            final_value = result['final_value']
            start = result['start']
            end = result['end']
            initial_cash = result['initial_cash']

            try:
                metrics = self._calculate_metrics(
                    cerebro=cerebro,
                    final_value=final_value,
                    start=start,
                    end=end,
                    initial_cash=initial_cash,
                )
                metrics_by_strategy[strategy_name] = metrics
            except Exception as e:
                # If metric calculation fails for a strategy, record error
                metrics_by_strategy[strategy_name] = {
                    'error': f"Failed to calculate metrics: {str(e)}"
                }

        return metrics_by_strategy

    def _calculate_metrics(
        self,
        cerebro: Any,
        final_value: float,
        start: datetime,
        end: datetime,
        initial_cash: float,
    ) -> dict[str, Any]:
        """Calculate all metrics for a single strategy."""

        # Extract analyzers
        strats = cerebro.runstrats
        if not strats or len(strats) == 0:
            raise ValueError("No strategy results found in cerebro")

        strat = strats[0][0]  # First strategy instance

        # Get analyzer results
        sharpe_analyzer = getattr(strat.analyzers, 'sharpe', None)
        drawdown_analyzer = getattr(strat.analyzers, 'drawdown', None)
        returns_analyzer = getattr(strat.analyzers, 'returns', None)

        # Extract Sharpe ratio
        sharpe_ratio = None
        if sharpe_analyzer:
            sharpe_dict = sharpe_analyzer.get_analysis()
            sharpe_ratio = sharpe_dict.get('sharperatio', None)

        # Extract max drawdown
        max_drawdown = None
        if drawdown_analyzer:
            dd_dict = drawdown_analyzer.get_analysis()
            max_drawdown = dd_dict.get('max', {}).get('drawdown', None)
            if max_drawdown is not None:
                max_drawdown = max_drawdown / 100.0  # Convert percentage to decimal

        # Extract returns data for volatility and win rate
        returns_data = None
        if returns_analyzer:
            returns_dict = returns_analyzer.get_analysis()
            returns_data = returns_dict.get('rtot', None)  # Total returns

        # Calculate CAGR
        total_return = (final_value - initial_cash) / initial_cash
        years = (end - start).days / 365.25
        if years > 0:
            cagr = (1 + total_return) ** (1 / years) - 1
        else:
            cagr = 0.0

        # Calculate Calmar ratio (CAGR / Max Drawdown)
        calmar_ratio = None
        if max_drawdown is not None and max_drawdown != 0:
            calmar_ratio = cagr / max_drawdown
        elif max_drawdown == 0:
            calmar_ratio = float('inf')  # No drawdown = infinite Calmar

        # Calculate win rate and volatility from returns
        win_rate = None
        volatility = None
        if returns_data is not None and len(returns_data) > 0:
            returns_array = np.array(list(returns_data.values()))
            win_rate = (returns_array > 0).sum() / len(returns_array)
            # Annualized volatility (assuming daily returns)
            volatility = np.std(returns_array) * np.sqrt(252)

        return {
            'final_value': final_value,
            'total_return': total_return,
            'cagr': cagr,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'calmar_ratio': calmar_ratio,
            'win_rate': win_rate,
            'volatility': volatility,
        }
