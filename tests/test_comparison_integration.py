"""Integration tests for strategy comparison mode."""

import subprocess
import sys
from pathlib import Path


def test_comparison_mode_all_strategies():
    """
    Integration test: --compare flag runs all strategies (DCA, Buy & Hold, TrendFollowing, MeanReversion)
    and produces clean output without log spam.

    Verifies:
    1. All strategies appear in comparison table
    2. Table header is present ("STRATEGY COMPARISON")
    3. No trade log spam (no "BUY SIGNAL" or "SELL SIGNAL" messages)
    4. Comparison table is readable (not buried in logs)

    Note: This test requires Alpaca API credentials in local_settings.py
    and a working internet connection to fetch market data.
    """
    # Run comparison mode on a known date range (4-year bull market)
    cmd = [
        sys.executable,  # Use same Python interpreter as test
        "main.py",
        "--compare",
        "--symbol", "SPY",
        "--start", "2020-01-01",
        "--end", "2023-12-31",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,  # 1 minute timeout
    )

    stdout = result.stdout
    stderr = result.stderr

    # Assert command succeeded
    assert result.returncode == 0, \
        f"Command failed with exit code {result.returncode}\nSTDERR: {stderr}\nSTDOUT: {stdout}"

    # Verify comparison table header appears
    assert "STRATEGY COMPARISON" in stdout, \
        "Expected comparison table header in output"

    # Verify all strategies appear in table
    assert "DCA" in stdout, "Expected DCA strategy in comparison table"
    assert "Buy & Hold" in stdout, "Expected Buy & Hold strategy in comparison table"
    assert "TrendFollowing" in stdout or "Trend" in stdout, \
        "Expected TrendFollowing strategy in comparison table"
    assert "MeanReversion" in stdout or "Mean" in stdout, \
        "Expected MeanReversion strategy in comparison table"

    # Verify NO trade log spam from TrendFollowing or MeanReversion (printlog should be suppressed)
    assert "BUY SIGNAL" not in stdout, \
        "Found 'BUY SIGNAL' in output - Strategy logs not suppressed in comparison mode"
    assert "SELL SIGNAL" not in stdout, \
        "Found 'SELL SIGNAL' in output - Strategy logs not suppressed in comparison mode"
    assert "BUY (MEAN REVERSION)" not in stdout, \
        "Found 'BUY (MEAN REVERSION)' in output - MeanReversion logs not suppressed in comparison mode"

    # Verify table metrics columns are present
    assert "CAGR" in stdout or "CAGR %" in stdout, "Expected CAGR column"
    assert "Sharpe" in stdout, "Expected Sharpe column"
    assert "Max DD" in stdout or "Drawdown" in stdout, "Expected Max Drawdown column"
    assert "Daily exposure/cash CSV saved to:" in stdout, \
        "Expected CSV export confirmation message in output"

    # Verify CSV file was written and has expected schema
    csv_files = sorted(Path(".").glob("comparison_exposure_SPY_2020-01-01_2023-12-31_*.csv"))
    assert csv_files, "Expected comparison exposure CSV file to be created"
    csv_text = csv_files[-1].read_text(encoding="utf-8")
    assert "date,strategy,portfolio_value,available_cash,exposure,cash_pct,exposure_pct" in csv_text, \
        "Expected long-format CSV headers"
    assert "DCA" in csv_text and "Buy & Hold" in csv_text, \
        "Expected multiple strategy rows in CSV output"

    print("✓ Integration test passed: 3-strategy comparison produces clean output")


def test_comparison_mode_short_period_insufficient_data():
    """
    Integration test: TrendFollowing on short backtest (< 200 bars) shows
    INSUFFICIENT DATA instead of misleading 0% metrics.

    Verifies zero-trade detection works in full pipeline.
    """
    # Run comparison on 3-month period (too short for SMA(200) warm-up)
    cmd = [
        sys.executable,
        "main.py",
        "--compare",
        "--symbol", "SPY",
        "--start", "2023-06-01",
        "--end", "2023-09-01",  # ~60 trading days
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )

    stdout = result.stdout

    # Should succeed (not crash)
    assert result.returncode == 0, f"Command failed: {result.stderr}"

    # TrendFollowing should show INSUFFICIENT DATA or ERROR
    # (Exact format depends on implementation - check for either)
    trend_following_line_found = False
    insufficient_data_indicated = False

    for line in stdout.split('\n'):
        if 'Trend' in line or 'TREND' in line:
            trend_following_line_found = True
            if 'INSUFFICIENT DATA' in line or 'ERROR' in line or 'No trades' in line:
                insufficient_data_indicated = True
                break

    assert trend_following_line_found, \
        "TrendFollowing strategy not found in output"
    assert insufficient_data_indicated, \
        "TrendFollowing should show INSUFFICIENT DATA for short backtest, " \
        f"but got:\n{stdout}"

    print("✓ Integration test passed: Short period triggers INSUFFICIENT DATA warning")


if __name__ == '__main__':
    # Simple test runner until pytest is bootstrapped
    print("Running test_comparison_mode_all_strategies...")
    print("(This test requires Alpaca API credentials and internet connection)\n")

    try:
        test_comparison_mode_all_strategies()
    except AssertionError as e:
        print(f"✗ FAIL: {e}\n")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("✗ FAIL: Test timed out (> 60 seconds)\n")
        sys.exit(1)
    except Exception as e:
        print(f"✗ FAIL: Unexpected error: {e}\n")
        sys.exit(1)

    print("\nRunning test_comparison_mode_short_period_insufficient_data...")
    try:
        test_comparison_mode_short_period_insufficient_data()
    except AssertionError as e:
        print(f"✗ FAIL: {e}\n")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("✗ FAIL: Test timed out (> 30 seconds)\n")
        sys.exit(1)
    except Exception as e:
        print(f"✗ FAIL: Unexpected error: {e}\n")
        sys.exit(1)

    print("\n" + "="*60)
    print("All integration tests passed!")
    print("="*60)
