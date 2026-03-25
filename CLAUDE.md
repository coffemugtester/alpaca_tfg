# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python backtesting framework for algorithmic trading strategies using historical data from the Alpaca Markets API. Strategies are simulated using the [Backtrader](https://www.backtrader.com/) engine.

## Running the Backtester

```bash
python main.py --symbol SPY --start 2020-01-01 --end 2023-12-31 --strategy bnh --cash 10000 --commission 0.0
```

**Required args:** `--symbol`, `--start`, `--end`, `--strategy` (`dca` or `bnh`)
**Optional args:** `--cash` (default 10000), `--commission` (default 0.0)

## Type Checking

```bash
mypy .
```

Configured in `mypy.ini` targeting Python 3.11 with `ignore_missing_imports = True`.

## Architecture

```
main.py                        # CLI entry point → calls backtesting/runner.py
config.py                      # Constants (CASH_DEFAULT, COMMISSION_DEFAULT) + Alpaca client factory
local_settings.py              # Alpaca API credentials (gitignored — create locally)
backtesting/
  runner.py                    # Orchestrates: fetch data → adapt → Cerebro → run
  data_adapter.py              # Converts Pandas DataFrame to Backtrader PandasData feed
data/
  alpaca_data.py               # Fetches OHLCV bars from Alpaca StockHistoricalDataClient
strategies/
  dca.py                       # Dollar-Cost Averaging: buys $100/month
  buy_and_hold.py              # Buys ~99.5% of cash on first bar, holds forever
  buy_first_sell_in_stop.py    # Experimental — not wired into main.py
```

**Data flow:** `main.py` → `runner.py` → `alpaca_data.fetch_daily_bars()` → `data_adapter.df_to_bt_feed()` → Backtrader Cerebro engine → Strategy `next()` called per bar → `stop()` generates matplotlib plot.

## Adding a New Strategy

1. Create `strategies/your_strategy.py` — subclass `bt.Strategy`
2. Implement `next()` for per-bar logic and `stop()` for end-of-run reporting
3. Register the strategy in `main.py`'s argument parser and strategy map

## Local Setup

Requires a `local_settings.py` at the project root with Alpaca credentials:

```python
ALPACA_API_KEY = "your_key"
ALPACA_SECRET_KEY = "your_secret"
```

**Dependencies** (no requirements.txt — install manually):
`alpaca-py`, `backtrader`, `pandas`, `matplotlib`

## gstack

For all web browsing, use the `/browse` skill from gstack. Never use `mcp__claude-in-chrome__*` tools.

**Available gstack skills:**
`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/review`, `/ship`, `/browse`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`

If gstack skills aren't available, run `/gstack-upgrade` to install them.

## Planned Work

See `TODO.md` for planned performance metrics: total return, CAGR, Sharpe ratio, max drawdown, Calmar ratio, etc.
