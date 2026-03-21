"""Unit tests for BasicMetricsStage."""

from datetime import datetime, timezone
from unittest.mock import Mock

from backtesting.validation.stages.basic_metrics import BasicMetricsStage


def test_zero_trades_shows_insufficient_data():
    """
    Test that when a strategy makes 0 trades (final_value ≈ initial_cash),
    the metrics stage returns an error indicator instead of misleading 0% metrics.

    This prevents users from seeing "0% CAGR, 0 Sharpe" when the real issue
    is that the strategy never entered a position (e.g., due to indicator warm-up).
    """
    stage = BasicMetricsStage()

    # Mock strategy result where no trades occurred
    # final_value == initial_cash (within floating point tolerance)
    initial_cash = 10000.0
    final_value = 10000.0  # Exactly the same - no value change

    # Create mock cerebro with empty strategy (no trades)
    mock_cerebro = Mock()
    mock_strat = Mock()
    mock_cerebro.runstrats = [[mock_strat]]

    # Mock analyzers - all return None or empty data
    mock_sharpe = Mock()
    mock_sharpe.get_analysis.return_value = {}
    mock_strat.analyzers.sharpe = mock_sharpe

    mock_drawdown = Mock()
    mock_drawdown.get_analysis.return_value = {}
    mock_strat.analyzers.drawdown = mock_drawdown

    mock_timereturn = Mock()
    mock_timereturn.get_analysis.return_value = {}  # Empty dict - no returns data
    mock_strat.analyzers.timereturn = mock_timereturn

    strategy_results = [{
        'strategy_name': 'ZeroTradeStrategy',
        'cerebro': mock_cerebro,
        'final_value': final_value,
        'start': datetime(2023, 1, 1, tzinfo=timezone.utc),
        'end': datetime(2023, 6, 30, tzinfo=timezone.utc),
        'initial_cash': initial_cash,
    }]

    # Run the stage
    metrics_by_strategy = stage.run(strategy_results)

    # Assert that the result indicates insufficient data
    assert 'ZeroTradeStrategy' in metrics_by_strategy
    metrics = metrics_by_strategy['ZeroTradeStrategy']

    # Should have an error key indicating insufficient data
    assert 'error' in metrics or 'insufficient_data' in metrics, \
        "Expected error or insufficient_data flag for zero-trade scenario"

    # Should NOT have misleading 0% CAGR metrics
    if 'error' in metrics:
        assert 'INSUFFICIENT DATA' in metrics['error'] or 'No trades' in metrics['error'], \
            f"Expected INSUFFICIENT DATA error, got: {metrics['error']}"


def test_normal_strategy_computes_metrics():
    """
    Test that a strategy with actual trades gets proper metrics computed.

    This is a regression test to ensure zero-trade detection doesn't
    break normal metric calculation.
    """
    stage = BasicMetricsStage()

    initial_cash = 10000.0
    final_value = 15000.0  # 50% gain

    # Create mock cerebro with actual returns
    mock_cerebro = Mock()
    mock_strat = Mock()
    mock_cerebro.runstrats = [[mock_strat]]

    # Mock analyzers with actual data
    mock_sharpe = Mock()
    mock_sharpe.get_analysis.return_value = {'sharperatio': 1.5}
    mock_strat.analyzers.sharpe = mock_sharpe

    mock_drawdown = Mock()
    mock_drawdown.get_analysis.return_value = {'max': {'drawdown': 10.5}}  # 10.5%
    mock_strat.analyzers.drawdown = mock_drawdown

    mock_timereturn = Mock()
    # Simulate some returns data (daily returns)
    mock_timereturn.get_analysis.return_value = {
        datetime(2023, 1, 5): 0.01,
        datetime(2023, 1, 6): -0.005,
        datetime(2023, 1, 9): 0.02,
        datetime(2023, 1, 10): 0.015,
    }
    mock_strat.analyzers.timereturn = mock_timereturn

    strategy_results = [{
        'strategy_name': 'ProfitableStrategy',
        'cerebro': mock_cerebro,
        'final_value': final_value,
        'start': datetime(2020, 1, 1, tzinfo=timezone.utc),
        'end': datetime(2023, 12, 31, tzinfo=timezone.utc),
        'initial_cash': initial_cash,
    }]

    # Run the stage
    metrics_by_strategy = stage.run(strategy_results)

    # Assert metrics are computed
    assert 'ProfitableStrategy' in metrics_by_strategy
    metrics = metrics_by_strategy['ProfitableStrategy']

    # Should NOT have error
    assert 'error' not in metrics
    assert 'insufficient_data' not in metrics

    # Should have actual metrics
    assert 'cagr' in metrics
    assert 'sharpe_ratio' in metrics
    assert 'max_drawdown' in metrics
    assert 'final_value' in metrics

    assert metrics['final_value'] == final_value
    assert metrics['sharpe_ratio'] == 1.5
    assert metrics['max_drawdown'] == 0.105  # 10.5% converted to decimal


if __name__ == '__main__':
    # Simple test runner until pytest is bootstrapped
    print("Running test_zero_trades_shows_insufficient_data...")
    try:
        test_zero_trades_shows_insufficient_data()
        print("✓ PASS")
    except AssertionError as e:
        print(f"✗ FAIL: {e}")

    print("\nRunning test_normal_strategy_computes_metrics...")
    try:
        test_normal_strategy_computes_metrics()
        print("✓ PASS")
    except AssertionError as e:
        print(f"✗ FAIL: {e}")

    print("\nDone.")
