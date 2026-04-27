# Alpaca Backtest Framework

Python backtesting framework for algorithmic trading strategies using historical data from the Alpaca Markets API. Strategies are simulated using the [Backtrader](https://www.backtrader.com/) engine.

## Features

- **6 Built-in Strategies**: DCA, Buy & Hold, Trend Following, Mean Reversion, Dinámica, Tactical Trend Dip
- **Multi-Asset Analysis**: Compare strategies across multiple assets simultaneously
- **Comprehensive Metrics**: Sharpe ratio, max drawdown, total return, order count, and more
- **CSV Export**: Automatic export of results for further analysis
- **Flexible CLI**: Three distinct modes for different analysis needs

## Requirements

- Python 3.11+
- Dependencies: `alpaca-py`, `backtrader`, `pandas`, `matplotlib`

## Installation

1. Clone the repository
2. Install dependencies (no requirements.txt - install manually):
   ```bash
   pip install alpaca-py backtrader pandas matplotlib
   ```
3. Create `local_settings.py` with your Alpaca credentials:
   ```python
   ALPACA_API_KEY = "your_key"
   ALPACA_SECRET_KEY = "your_secret"
   ```

## Usage

The framework provides three subcommands for different analysis scenarios:

### 1. Single Strategy Mode

Run a single strategy on a single asset.

```bash
python main.py single --symbol SPY --strategy dca --start 2016-01-01 --end 2026-01-01
```

**Available strategies**: `dca`, `bnh`, `trendfollowing`, `meanreversion`, `dinamica`, `tacticaltrenddip`

**Optional flags**:
- `--plot`: Show matplotlib chart at end
- `--cash`: Initial cash (default: 10000)
- `--commission`: Commission percentage (default: 0.02%)
- `--slippage`: Slippage percentage (default: 0.03%)

**Example**:
```bash
python main.py single --symbol AAPL --strategy dinamica --plot --cash 50000
```

### 2. Compare-Single Mode

Compare all 6 strategies on a single asset.

```bash
python main.py compare-single --symbol SPY --start 2016-01-01 --end 2026-01-01
```

**Output**:
- Terminal: Comparison table showing all metrics
- Charts: 2 matplotlib charts (portfolio value + drawdown)
- CSV: Timestamped daily exposure CSV in `csv_output/` directory

**Example**:
```bash
python main.py compare-single --symbol QQQ --cash 25000
```

### 3. Compare-Multi Mode

Compare all 6 strategies across multiple assets (default: 8 assets).

```bash
python main.py compare-multi
```

**Default assets**: SPY, QQQ, IWM, GLD, TLT, AAPL, AMD, XLE

**Custom asset list**:
```bash
python main.py compare-multi --symbols SPY QQQ AAPL MSFT
```

**Output**:
- Terminal: Per-asset comparison tables + multi-asset summary table
- CSV: Appends results to `global_comparison/comparison_results.csv` (cumulative file)

**Note**: `--plot` flag is ignored in multi-asset mode to avoid opening too many windows.

## Strategies

### DCA (Dollar-Cost Averaging)
Spreads initial cash evenly across all months. Buys a fixed amount on the first trading day of each month regardless of price.

### Buy & Hold
Invests 99.5% of capital on the first available trading day and holds the position indefinitely.

### Trend Following
Dynamic monthly redistribution strategy with trend filters:
- Only enters when price > 200 SMA and 50 SMA > 200 SMA
- Requires MACD momentum confirmation
- RSI strength filter (50-70 range)
- One entry maximum per month

### Mean Reversion
Buys dips during uptrends using RSI oversold signals:
- Trend filter: Price must be above 200 SMA
- Entry trigger: RSI < 30 (oversold)
- Dynamic monthly budget redistribution

### Dinámica
Enhanced DCA with tactical timing signals (currently in development).

### Tactical Trend Dip
Progressive capital deployment using technical signals:
- Avoids buying during weak macro trends
- Buys pullbacks inside uptrends (RSI < 40)
- Adds on renewed momentum (MACD crossover)
- Adds on breakout strength (60-day high break)

## Output Files

### Daily Exposure CSV (compare-single mode)
Location: `csv_output/comparison_exposure_{SYMBOL}_{START}_{END}_{TIMESTAMP}.csv`

Columns: `date`, `strategy`, `portfolio_value`, `available_cash`, `exposure`, `cash_pct`, `exposure_pct`, `amount_moved`

### Summary Results CSV (compare-multi mode)
Location: `global_comparison/comparison_results.csv`

Columns: `asset`, `strategy`, `final_value`, `total_return_pct`, `sharpe_ratio`, `max_drawdown_pct`, `unused_cash`, `order_count`

**Note**: This file uses append mode, accumulating results across multiple runs for benchmarking.

## Examples

**Test a new strategy on SPY**:
```bash
python main.py single --symbol SPY --strategy tacticaltrenddip --plot
```

**Compare all strategies on a single asset**:
```bash
python main.py compare-single --symbol AAPL --start 2020-01-01 --end 2024-01-01
```

**Run full multi-asset benchmark**:
```bash
# Clear previous results
rm global_comparison/comparison_results.csv

# Run comparison on all 8 default assets
python main.py compare-multi
```

**Custom multi-asset comparison**:
```bash
python main.py compare-multi --symbols SPY QQQ IWM --cash 50000
```

## Architecture

```
main.py                        # CLI entry point with subcommand routing
config.py                      # Constants and Alpaca client factory
local_settings.py              # Alpaca API credentials (gitignored)

backtesting/
  runner.py                    # Single-strategy execution
  data_adapter.py              # Pandas → Backtrader conversion
  strategy_comparison.py       # Multi-strategy comparison engine
  validation/
    pipeline.py                # ValidationPipeline for compare-single mode
    stages/
      basic_metrics.py         # Advanced metrics calculation

data/
  alpaca_data.py               # Fetches OHLCV bars from Alpaca API

strategies/
  dca.py                       # Dollar-Cost Averaging
  buy_and_hold.py              # Buy & Hold
  trendfollow.py               # Trend Following
  meanreversion.py             # Mean Reversion
  dinamica.py                  # Dinámica (experimental)
  tacticaltrenddip.py          # Tactical Trend Dip
```

## Configuration

Edit `config.py` to modify:
- `CASH_DEFAULT`: Initial cash (default: 10000)
- `COMMISSION_DEFAULT`: Commission rate (default: 0.0002 = 0.02%)
- `SLIPPAGE_DEFAULT`: Slippage rate (default: 0.0003 = 0.03%)

## Type Checking

```bash
mypy .
```

Configured in `mypy.ini` targeting Python 3.11 with `ignore_missing_imports = True`.

## Adding a New Strategy

1. Create `strategies/your_strategy.py` - subclass `bt.Strategy`
2. Implement `next()` for per-bar logic
3. Implement `stop()` for end-of-run reporting (must respect `self.p.show_plot`)
4. Add `show_plot=True` parameter to strategy params
5. Register in `main.py`'s `STRATEGY_REGISTRY`:
   ```python
   STRATEGY_REGISTRY = {
       # ... existing entries
       "yourstrategy": ("YourStrategy", YourStrategyClass),
   }
   ```
6. Update parameter handling in `backtesting/strategy_comparison.py` if needed

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
