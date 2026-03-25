"""Validation pipeline for comparing multiple trading strategies."""

from __future__ import annotations

from datetime import datetime
from typing import Type

import backtrader as bt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend to suppress plot windows

from backtesting.runner import run_backtest
from data.alpaca_data import fetch_daily_bars
from backtesting.data_adapter import df_to_bt_feed
from config import calculate_months_between
from strategies.dca import DollarCostAveraging
from strategies.trendfollow import TrendFollowingStrategy
from strategies.meanreversion import MeanReversionStrategy
from .stages.basic_metrics import BasicMetricsStage


class ValidationPipeline:
    """
    Orchestrates strategy comparison workflow.

    Responsibilities:
    - Fetch market data once (cached, reused across strategies)
    - Run each strategy through Backtrader with analyzers attached
    - Extract metrics via BasicMetricsStage
    - Format and display comparison table
    """

    def __init__(
        self,
        strategies: dict[str, Type[bt.Strategy]],
        symbol: str,
        start: datetime,
        end: datetime,
        cash: float,
        commission: float,
    ):
        """
        Initialize the validation pipeline.

        Args:
            strategies: Dict mapping strategy name to strategy class
            symbol: Ticker symbol to backtest
            start: Start date
            end: End date
            cash: Initial cash
            commission: Commission rate
        """
        self.strategies = strategies
        self.symbol = symbol
        self.start = start
        self.end = end
        self.cash = cash
        self.commission = commission

    def run_comparison(self) -> None:
        """
        Run all strategies and display comparison table.

        This is the main entry point for the comparison workflow.
        """
        print(f"\nFetching data for {self.symbol} from {self.start.date()} to {self.end.date()}...")

        # Fetch data once, reuse across all strategies (Perf A decision)
        try:
            df = fetch_daily_bars(symbol=self.symbol, start=self.start, end=self.end)
        except Exception as e:
            print(f"ERROR: Failed to fetch data from Alpaca API: {e}")
            return

        if df is None or len(df) == 0:
            print(f"ERROR: No data returned for {self.symbol} in the specified date range.")
            return

        print(f"Loaded {len(df)} bars.\n")

        # Convert to Backtrader feed (cached for reuse)
        data_feed = df_to_bt_feed(df)

        # Run each strategy and collect results
        strategy_results = []
        for strategy_name, strategy_cls in self.strategies.items():
            print(f"Running {strategy_name}...")

            try:
                result = self._run_single_strategy(
                    strategy_cls=strategy_cls,
                    strategy_name=strategy_name,
                    data_feed=data_feed,
                )
                strategy_results.append(result)
            except Exception as e:
                print(f"  ERROR: Strategy {strategy_name} crashed: {e}")
                # Continue with other strategies (partial results)
                strategy_results.append({
                    'strategy_name': strategy_name,
                    'error': str(e),
                })

        # Extract metrics using BasicMetricsStage
        metrics_stage = BasicMetricsStage()
        # Filter out errored strategies before passing to metrics stage
        valid_results = [r for r in strategy_results if 'error' not in r]
        metrics_by_strategy = metrics_stage.run(valid_results)

        # Merge error info for strategies that crashed
        for result in strategy_results:
            if 'error' in result:
                metrics_by_strategy[result['strategy_name']] = {'error': result['error']}

        # Display comparison table
        self._print_comparison_table(metrics_by_strategy)

    def _run_single_strategy(
        self,
        strategy_cls: Type[bt.Strategy],
        strategy_name: str,
        data_feed: bt.feeds.PandasData,
    ) -> dict:
        """
        Run a single strategy with analyzers attached.

        Args:
            strategy_cls: Strategy class to run
            strategy_name: Name of the strategy
            data_feed: Backtrader data feed

        Returns:
            Dict with strategy results including cerebro instance
        """
        # Create Cerebro instance
        cerebro = bt.Cerebro()

        # Add data feed
        cerebro.adddata(data_feed, name=self.symbol)

        # Add strategy with parameters
        # DCA spreads initial cash evenly over all months
        if strategy_cls == DollarCostAveraging:
            num_months = calculate_months_between(self.start, self.end)
            monthly_invest = self.cash / num_months
            cerebro.addstrategy(strategy_cls, monthly_invest=monthly_invest)
        # TrendFollowing: suppress trade logs in comparison mode
        elif strategy_cls == TrendFollowingStrategy:
            cerebro.addstrategy(strategy_cls, printlog=False)
        # MeanReversion: suppress trade logs in comparison mode
        elif strategy_cls == MeanReversionStrategy:
            cerebro.addstrategy(strategy_cls, printlog=False)
        else:
            cerebro.addstrategy(strategy_cls)

        # Set broker parameters
        cerebro.broker.setcash(self.cash)
        cerebro.broker.setcommission(commission=self.commission)

        # Attach analyzers (Issue 1: TimeReturn for equity curve, Issue 2: Pipeline attaches)
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn')

        # Run backtest (Issue 7: verbose=False, plot=False for comparison mode)
        # Note: We're not using the modified run_backtest() here because we need
        # more control over analyzer attachment. We run cerebro directly.
        cerebro.run()

        final_value = float(cerebro.broker.getvalue())

        return {
            'strategy_name': strategy_name,
            'cerebro': cerebro,
            'final_value': final_value,
            'start': self.start,
            'end': self.end,
            'initial_cash': self.cash,
        }

    def _print_comparison_table(self, metrics_by_strategy: dict) -> None:
        """
        Print comparison table using built-in string formatting (Issue 4: no rich/tabulate).

        Args:
            metrics_by_strategy: Dict mapping strategy name to metrics dict
        """
        print("\n" + "="*80)
        print("STRATEGY COMPARISON")
        print("="*80)

        if not metrics_by_strategy:
            print("No results to display.")
            return

        # Table header
        header = (
            f"{'Strategy':<20} "
            f"{'Final Value':>12} "
            f"{'Total Ret %':>11} "
            f"{'CAGR %':>8} "
            f"{'Sharpe':>7} "
            f"{'Max DD %':>9} "
            f"{'Calmar':>7}"
        )
        print(header)
        print("-"*80)

        # Table rows
        for strategy_name, metrics in metrics_by_strategy.items():
            if 'error' in metrics:
                # Show error row
                row = f"{strategy_name:<20} ERROR: {metrics['error']}"
                print(row)
            else:
                # Format metrics
                final_value = metrics.get('final_value', 0)
                total_return = metrics.get('total_return', 0) * 100
                cagr = metrics.get('cagr', 0) * 100
                sharpe = metrics.get('sharpe_ratio', None)
                max_dd = metrics.get('max_drawdown', None)
                calmar = metrics.get('calmar_ratio', None)

                # Handle None values
                sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"
                max_dd_str = f"{max_dd*100:.2f}" if max_dd is not None else "N/A"

                if calmar == float('inf'):
                    calmar_str = "Inf"
                elif calmar is not None:
                    calmar_str = f"{calmar:.3f}"
                else:
                    calmar_str = "N/A"

                row = (
                    f"{strategy_name:<20} "
                    f"${final_value:>11,.2f} "
                    f"{total_return:>10.2f}% "
                    f"{cagr:>7.2f}% "
                    f"{sharpe_str:>7} "
                    f"{max_dd_str:>8}% "
                    f"{calmar_str:>7}"
                )
                print(row)

        print("="*80 + "\n")
