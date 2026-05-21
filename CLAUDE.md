# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python backtesting framework for algorithmic trading strategies using historical data from the Alpaca Markets API. Strategies are simulated using the [Backtrader](https://www.backtrader.com/) engine with support for both daily and intraday (1-minute) data.

## Running the Backtester

### Single Strategy Test
```bash
python main.py --symbol SPY --start 2020-01-01 --end 2023-12-31 --strategy bnh --cash 10000 --commission 0.0
```

**Required args:** `--symbol`, `--start`, `--end`, `--strategy`
**Optional args:** `--cash` (default 10000), `--commission` (default 0.0)

### Multi-Strategy Comparison (Recommended)
```bash
python commands.py compare-multi --symbol SPY --start 2016-01-01 --end 2026-01-01
```

Runs all strategies on the symbol and exports comprehensive comparison CSV with deltas vs Buy & Hold and DCA baselines.

### Parallel Multi-Asset Backtests
```bash
python commands.py compare-multi --symbols SPY QQQ IWM --parallel --start 2016-01-01 --end 2026-01-01
```

Uses ProcessPoolExecutor to run multiple assets in parallel. Pre-fetches data to avoid cache write conflicts.

## Available Strategies

Strategy registry in `commands.py:39-46`:

| CLI Name | Display Name | Class | Timeframe | Description |
|----------|--------------|-------|-----------|-------------|
| `dca` | DCA | `DollarCostAveraging` | daily | Fixed monthly investment, no timing |
| `bnh` | Buy & Hold | `BuyAndHold` | daily | Buy 99.5% on first bar, hold forever |
| `tacticalmonthly` | DCA Táctico | `TacticalMonthlyRedistributed` | daily | Monthly DCA with accumulated reserve + technical entry filters |
| `tacticalatrmonthly` | Corrección Táctica | `TacticalAtrMonthly` | daily | Tactical trend + dip reserve with drawdown-based exposure scaling |
| `intradayvol` | Intraday Vol Bands | `IntradayVolatilityBands` | minute | Intraday volatility bands with +6% take profit, 2.5x leverage sizing |
| `intradaytacticaldca` | Intraday Tactical DCA | `IntradayTacticalDCA` | minute | Multi-timeframe: daily regime filters + intraday execution below daily BB lower band |

## Architecture

```
commands.py                    # CLI subcommands (compare-multi, etc.) + strategy registry
main.py                        # Legacy single-strategy runner
config.py                      # Constants + Alpaca client factory
local_settings.py              # Alpaca API credentials (gitignored — create locally)

backtesting/
  runner.py                    # Orchestrates: fetch data → adapt → Cerebro → run
  strategy_comparison.py       # Multi-strategy comparison engine + CSV export
  data_adapter.py              # Converts Pandas DataFrame to Backtrader PandasData feed
  validation.py                # ValidationPipeline for backtest integrity checks

data/
  alpaca_data.py               # Fetches daily/minute OHLCV bars from Alpaca API
  alpaca_cache.py              # SQLite cache layer (2.6GB, gitignored)

strategies/
  dca.py                       # Dollar-Cost Averaging
  buy_and_hold.py              # Buy & Hold baseline
  tacticalmonthly.py           # DCA Táctico (accumulated reserve + timing)
  tacticalatrmonthly.py        # Corrección Táctica (drawdown-based scaling)
  intraday_volatility_bands.py # Intraday Vol Bands (6% take profit)
  intraday_tactical_dca.py     # Intraday Tactical DCA (multi-timeframe)

global_comparison/             # Output directory (gitignored)
  comparison_results.csv       # Main results: all strategies × all assets
  trade_analytics_{SYMBOL}.csv # Per-asset trade logs (entry/exit details)
  entry_analytics_{SYMBOL}.csv # Fallback for strategies with no completed exits
```

**Data flow:**
1. `commands.py` → fetch data (with cache check)
2. `strategy_comparison.py` → run all strategies via Cerebro
3. Calculate metrics: final value, total return, CAGR, Sharpe, max drawdown, Calmar
4. Export to CSV with deltas vs Buy & Hold and DCA baselines

## Database Caching System

**Location:** `data/alpaca_cache.db` (SQLite, gitignored)

**Purpose:** Eliminate redundant Alpaca API calls for immutable historical data

**Implementation:** `data/alpaca_cache.py`
- Tables: `daily_bars`, `minute_bars`
- Primary keys: `(symbol, date)` for daily, `(symbol, timestamp)` for minute
- Cache-first strategy: query cache → if miss, fetch from API → store in cache

**Usage in fetch functions:** `data/alpaca_data.py:fetch_daily_bars()`, `fetch_minute_bars()`

```python
cache = AlpacaCache()
cached_df = cache.query_daily_bars(symbol, start, end)
if cached_df is not None:
    print(f"Cache HIT: {symbol} daily")
    return cached_df
# ... fetch from API, then cache.insert_daily_bars(symbol, df)
```

**Parallelization:** Pre-fetch data before parallel execution to avoid cache write conflicts

## Performance Metrics

Exported to `global_comparison/comparison_results.csv`:

**Core Metrics:**
- Final value (portfolio + cash)
- Total return %
- CAGR % (Compound Annual Growth Rate)
- Sharpe ratio (risk-free rate = 0)
- Max drawdown %
- Calmar ratio (CAGR / abs(max drawdown))
- Unused cash (final cash position)
- Order count

**Delta Metrics (vs baselines):**
- All above metrics with `_vs_bnh` and `_vs_dca` suffixes
- Example: `cagr_pct_vs_bnh` = strategy CAGR - Buy & Hold CAGR

**Asset Classification:**
- `type`: ETF or Stock
- `category`: Broad Market, Tech, Travel, Cruise, Energy, Gold, etc.
- Defined in `backtesting/strategy_comparison.py:23-68`

## Adding a New Strategy

1. **Create strategy file:** `strategies/your_strategy.py`
   - Subclass `bt.Strategy`
   - Implement `__init__()`, `next()`, `stop()`
   - For intraday strategies, expect `self.datas[0]` (minute) and `self.datas[1]` (daily)

2. **Register in commands.py:**
   ```python
   from strategies.your_strategy import YourStrategy

   STRATEGY_REGISTRY = {
       "yourname": ("Display Name", YourStrategy, "daily"),  # or "minute"
   }
   ```

3. **Test:**
   ```bash
   python commands.py compare-multi --symbol SPY --start 2020-01-01 --end 2023-12-31
   ```

## Multi-Timeframe Strategies

Strategies using intraday data with daily regime filters (e.g., Intraday Tactical DCA):

**Data feeds:**
- `self.datas[0]` = 1-minute bars (primary feed for execution)
- `self.datas[1]` = daily bars (for trend indicators like SMA200, Bollinger Bands)

**Runner support:** `backtesting/strategy_comparison.py:241-245`
```python
cerebro.adddata(data_feed, name=symbol)  # Minute data
if daily_feed is not None:
    cerebro.adddata(daily_feed, name=f"{symbol}_daily")  # Daily data
```

## Trade Analytics Export

Intraday strategies export detailed trade logs to `global_comparison/`:

**trade_analytics_{SYMBOL}.csv** (completed trades with exits):
- Columns: symbol, direction, entry_time, exit_time, entry_price, exit_price, stop_price, position_size, pnl_dollars, pnl_pct, exit_reason, hold_duration_hours, hold_duration_days

**entry_analytics_{SYMBOL}.csv** (fallback for open positions):
- Columns: symbol, action, entry_time, entry_price, position_size, value, commission
- Generated when strategy has entries but no exits (e.g., position held until end of backtest)

## Local Setup

**Requirements:**
```bash
pip install alpaca-py backtrader pandas matplotlib
```

**Credentials:** Create `local_settings.py` at project root:
```python
ALPACA_API_KEY = "your_key"
ALPACA_SECRET_KEY = "your_secret"
```

**Data cache:** First run will create `data/alpaca_cache.db` (~2.6GB for full dataset)

## Type Checking

```bash
mypy .
```

Configured in `mypy.ini` targeting Python 3.13 with `ignore_missing_imports = True`.

## Common Workflows

### Full Backtest Suite
```bash
# Run all strategies on default 17 assets (SPY, QQQ, IWM, AAPL, AMD, BKNG, etc.)
python commands.py compare-multi --parallel --start 2016-01-01 --end 2026-01-01
```

### Single Asset Analysis
```bash
# Compare all strategies on one asset
python commands.py compare-multi --symbol SPY --start 2016-01-01 --end 2026-01-01

# Check trade analytics
cat global_comparison/trade_analytics_SPY.csv
```

### Custom Asset List
```bash
python commands.py compare-multi --symbols AAPL MSFT GOOGL --parallel --start 2020-01-01 --end 2025-01-01
```

## Key Insights from Recent Analysis

**Strategy Performance by Category:**

| Strategy | Best For | Worst For | Key Metric |
|----------|----------|-----------|------------|
| Buy & Hold | Strong bull trends (tech, indices) | Crash-and-recover (cruise) | Highest returns on trending assets |
| DCA | Crash scenarios (cruise lines) | Strong bull markets | Buys dips automatically |
| DCA Táctico | Choppy markets | Strong trends | Timing reduces bad entries |
| Intraday Vol Bands | Volatile mean-reverting (EXPE, CCL) | Secular growth (AMD, AAPL) | 66.7% win rate on cruise, 0% on ETFs |
| Intraday Tactical DCA | TBD | TBD | Multi-timeframe precision entry |

**Critical Findings:**
- Intraday Vol Bands: No stop loss + 6% take profit = 70-90% drawdowns despite decent returns
- DCA beats strategy on crash recoveries (better average cost)
- Strategy beats DCA on trending markets (better timing)
- Calmar ratio reveals risk-adjusted truth: most tactical strategies have worse Sharpe than BnH

## gstack

For all web browsing, use the `/browse` skill from gstack. Never use `mcp__claude-in-chrome__*` tools.

**Available gstack skills:**
`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/review`, `/ship`, `/browse`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`

If gstack skills aren't available, run `/gstack-upgrade` to install them.
