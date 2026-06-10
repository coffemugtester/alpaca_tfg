"""Test to verify cash periods are flat."""
from datetime import datetime
from backtesting.strategy_comparison import run_strategy_comparison

# Run short period
result = run_strategy_comparison(
    symbol='QQQ',
    start=datetime(2017, 1, 1),
    end=datetime(2017, 3, 1),  # Period that should include exit and cash period
    cash=10000,
    commission=0.0002,
    slippage=0.0003,
    show_plots=False,
    strategies_with_timeframes={"Gestión Activa": ("strategies.intraday_volatility_bands", "minute")}
)

# Check time_series
ts = result['results'].get('Gestión Activa', {}).get('time_series', {})
dates = sorted(ts.keys())

print(f"Total snapshots: {len(dates)}")
if len(dates) > 0:
    print(f"First: {dates[0].date()}, Last: {dates[-1].date()}")

    # Show first 10 values
    print("\nFirst 10 daily portfolio values:")
    for i, dt in enumerate(dates[:10]):
        value = ts[dt]['portfolio_value']
        cash = ts[dt]['available_cash']
        print(f"  {dt.date()}: Portfolio=${value:.2f}, Cash=${cash:.2f}")