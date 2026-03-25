# Changelog

All notable changes to this project will be documented in this file.

## [0.0.1.0] - 2026-03-20

### Added
- **Strategy comparison mode** via `--compare` flag in main.py
  - Compare all registered strategies (DCA, Buy & Hold) side-by-side on identical market data
  - Metrics: CAGR, Sharpe Ratio, Max Drawdown, Calmar Ratio, Win Rate, Volatility
- **Validation pipeline framework** (`backtesting/validation/`)
  - `ValidationPipeline` class orchestrates multi-strategy backtests
  - `BasicMetricsStage` extracts performance metrics from Backtrader analyzers
  - DataFrame caching to avoid redundant Alpaca API calls
  - Error handling for API failures, strategy crashes, and division by zero
- **Comparison table output** using built-in string formatting (no new dependencies)
- `parse_date()` utility in config.py for date string parsing (DRY)

### Changed
- Made `--strategy` argument optional (required only in single-strategy mode)
- Suppress matplotlib plot windows in comparison mode using Agg backend

### Fixed
- N/A (initial feature release)
