"""Validation pipeline for comparing multiple trading strategies."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Type

import backtrader as bt
import matplotlib

from backtesting.runner import run_backtest
from data.alpaca_data import fetch_daily_bars
from backtesting.data_adapter import df_to_bt_feed
from config import calculate_months_between
from strategies.dca import DollarCostAveraging
from strategies.trendfollow import TrendFollowingStrategy
from strategies.meanreversion import MeanReversionStrategy
from .stages.basic_metrics import BasicMetricsStage


class _DailyAccountSnapshot(bt.Analyzer):
    """Capture daily portfolio value and available cash from broker state."""

    def start(self) -> None:
        self._rows: dict = {}

    def next(self) -> None:
        dt = self.strategy.datetime.datetime(0)
        self._rows[dt] = {
            "portfolio_value": float(self.strategy.broker.getvalue()),
            "available_cash": float(self.strategy.broker.getcash()),
        }

    def get_analysis(self) -> dict:
        return self._rows


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
        slippage: float,
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
            slippage: Slippage percentage
        """
        self.strategies = strategies
        self.symbol = symbol
        self.start = start
        self.end = end
        self.cash = cash
        self.commission = commission
        self.slippage = slippage

    def run_comparison(self) -> None:
        """
        Run all strategies and display comparison table.

        This is the main entry point for the comparison workflow.
        """
        # Suppress plots in comparison mode - use non-interactive backend
        matplotlib.use("Agg")

        print(
            f"\nFetching data for {self.symbol} from {self.start.date()} to {self.end.date()}..."
        )

        # Fetch data once, reuse across all strategies (Perf A decision)
        try:
            df = fetch_daily_bars(symbol=self.symbol, start=self.start, end=self.end)
        except Exception as e:
            print(f"ERROR: Failed to fetch data from Alpaca API: {e}")
            return

        if df is None or len(df) == 0:
            print(
                f"ERROR: No data returned for {self.symbol} in the specified date range."
            )
            return

        print(f"Loaded {len(df)} bars.\n")

        # Convert to Backtrader feed (cached for reuse)
        data_feed = df_to_bt_feed(df)

        # Run each strategy and collect results
        strategy_results = []
        for strategy_name, strategy_cls in self.strategies.items():
            print(f"Running {strategy_name}...")

            if strategy_name == "TrendFollowing":
                strategy_name = "Seguimiento"

            if strategy_name == "MeanReversion":
                strategy_name = "Reversión"

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
                strategy_results.append(
                    {
                        "strategy_name": strategy_name,
                        "error": str(e),
                    }
                )

        # Extract metrics using BasicMetricsStage
        metrics_stage = BasicMetricsStage()
        # Filter out errored strategies before passing to metrics stage
        valid_results = [r for r in strategy_results if "error" not in r]
        metrics_by_strategy = metrics_stage.run(valid_results)

        # Merge error info for strategies that crashed
        for result in strategy_results:
            if "error" in result:
                metrics_by_strategy[result["strategy_name"]] = {
                    "error": result["error"]
                }

        # Display comparison table
        self._print_comparison_table(metrics_by_strategy)

        # Export daily exposure/cash records for downstream analysis
        self._export_daily_exposure_csv(strategy_results)

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
        cerebro = bt.Cerebro(cheat_on_open=True)  # Enable next_open() callbacks

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
        cerebro.broker.set_slippage_perc(self.slippage)

        # Attach analyzers (Issue 1: TimeReturn for equity curve, Issue 2: Pipeline attaches)
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")
        # Daily account snapshots for CSV export (Backtrader-version agnostic).
        cerebro.addanalyzer(_DailyAccountSnapshot, _name="daily_account")

        # Run backtest (Issue 7: verbose=False, plot=False for comparison mode)
        # Note: We're not using the modified run_backtest() here because we need
        # more control over analyzer attachment. We run cerebro directly.
        cerebro.run()

        final_value = float(cerebro.broker.getvalue())

        return {
            "strategy_name": strategy_name,
            "cerebro": cerebro,
            "final_value": final_value,
            "start": self.start,
            "end": self.end,
            "initial_cash": self.cash,
        }

    def _print_comparison_table(self, metrics_by_strategy: dict) -> None:
        """
        Print comparison table using built-in string formatting (Issue 4: no rich/tabulate).

        Args:
            metrics_by_strategy: Dict mapping strategy name to metrics dict
        """
        print("\n" + "=" * 80)
        print("STRATEGY COMPARISON")
        print("=" * 80)

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
        print("-" * 80)

        # Table rows
        for strategy_name, metrics in metrics_by_strategy.items():
            if "error" in metrics:
                # Show error row
                row = f"{strategy_name:<20} ERROR: {metrics['error']}"
                print(row)
            else:
                # Format metrics
                final_value = metrics.get("final_value", 0)
                total_return = metrics.get("total_return", 0) * 100
                cagr = metrics.get("cagr", 0) * 100
                sharpe = metrics.get("sharpe_ratio", None)
                max_dd = metrics.get("max_drawdown", None)
                calmar = metrics.get("calmar_ratio", None)

                # Handle None values
                sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"
                max_dd_str = f"{max_dd*100:.2f}" if max_dd is not None else "N/A"

                if calmar == float("inf"):
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

        print("=" * 80 + "\n")

    def _extract_daily_exposure_rows(self, result: dict) -> list[dict]:
        """
        Extract normalized daily exposure/cash rows for a single strategy result.
        """
        strategy_name = result["strategy_name"]
        initial_cash = float(result["initial_cash"])
        strats = result["cerebro"].runstrats
        if not strats or len(strats) == 0:
            raise ValueError(f"No strategy output found for {strategy_name}")

        strat = strats[0][0]

        daily_account_analyzer = getattr(strat.analyzers, "daily_account", None)

        if daily_account_analyzer is None:
            raise ValueError(f"Missing analyzers for {strategy_name}")

        daily_account_data = daily_account_analyzer.get_analysis()
        if not isinstance(daily_account_data, dict) or len(daily_account_data) == 0:
            raise ValueError(f"No daily account data for {strategy_name}")

        rows: list[dict] = []

        for date_key in sorted(daily_account_data.keys()):
            snapshot = daily_account_data.get(date_key, {})
            if not isinstance(snapshot, dict):
                snapshot = {}

            portfolio_value = float(snapshot.get("portfolio_value", initial_cash))
            available_cash = float(snapshot.get("available_cash", 0.0))
            exposure = portfolio_value - available_cash
            if exposure < 0:
                # Guard against tiny floating-point underflow.
                exposure = 0.0

            if portfolio_value > 0:
                cash_pct = available_cash / portfolio_value
                exposure_pct = exposure / portfolio_value
            else:
                cash_pct = 0.0
                exposure_pct = 0.0

            # Keep percentages bounded for easier downstream validation.
            cash_pct = min(max(cash_pct, 0.0), 1.0)
            exposure_pct = min(max(exposure_pct, 0.0), 1.0)

            date_str = (
                date_key.date().isoformat()
                if hasattr(date_key, "date")
                else str(date_key)
            )
            rows.append(
                {
                    "date": date_str,
                    "strategy": strategy_name,
                    "portfolio_value": round(portfolio_value, 6),
                    "available_cash": round(available_cash, 6),
                    "exposure": round(exposure, 6),
                    "cash_pct": round(cash_pct, 8),
                    "exposure_pct": round(exposure_pct, 8),
                }
            )

        return rows

    def _export_daily_exposure_csv(self, strategy_results: list[dict]) -> None:
        """
        Export normalized long-format daily exposure/cash rows to CSV.
        """
        all_rows: list[dict] = []
        skipped: list[str] = []

        for result in strategy_results:
            if "error" in result:
                skipped.append(result["strategy_name"])
                continue

            try:
                all_rows.extend(self._extract_daily_exposure_rows(result))
            except Exception as exc:
                strategy_name = result.get("strategy_name", "unknown")
                skipped.append(strategy_name)
                print(f"WARNING: Skipping CSV export rows for {strategy_name}: {exc}")

        if not all_rows:
            print("WARNING: No exposure/cash rows were generated; skipping CSV export.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = (
            f"comparison_exposure_{self.symbol}_"
            f"{self.start.date()}_{self.end.date()}_{timestamp}.csv"
        )
        output_path = Path.cwd() / filename

        fieldnames = [
            "date",
            "strategy",
            "portfolio_value",
            "available_cash",
            "exposure",
            "cash_pct",
            "exposure_pct",
        ]

        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"Daily exposure/cash CSV saved to: {output_path}")
        if skipped:
            skipped_list = ", ".join(skipped)
            print(
                f"WARNING: CSV contains partial results. Skipped strategies: {skipped_list}"
            )
