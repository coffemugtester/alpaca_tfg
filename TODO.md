Estrategia algorítmica básica

Métricas de rendimiento:

- Retorno total
- CAGR
- Time-Weighted Return
- Money-Weighted Return
- Drawdown
- Max Drawdown
- Sharpe Ratio
- Calmar Ratio
- Consistencia: % de periodos positivos, volatilidad de retornos, duración de drawdowns

DevEx:

- list dependencies and whitelist them

## Pending

### Bootstrap pytest test framework

**What:** Set up pytest infrastructure with conftest.py for fixtures, add test data mocking for Alpaca API.

**Why:** Currently writing tests (zero-trade detection, integration tests) without a framework. Tests exist but can't be run systematically. Need infrastructure before test suite grows further.

**Pros:**
- Enables CI/CD with automated test runs
- Provides fixtures for mocking Backtrader/Alpaca dependencies
- Clear pass/fail reporting
- Standard Python testing workflow

**Cons:**
- Adds pytest dependency
- Requires minimal setup time (~30 min with CC)

**Context:** .gstack/no-test-bootstrap exists, indicating prior decision to defer. But as test count grows (unit test + integration test = 2+ test files so far), framework becomes necessary. Start with minimal setup: pytest install, basic conftest with Alpaca API mock, run with `pytest .`

**Depends on:** None (can do anytime)

---

### Parameter optimization for TrendFollowing strategy

**What:** Add grid search or genetic algorithm to find optimal parameter values for TrendFollowing (SMA periods, RSI thresholds, stop loss %, take profit %, etc.). New `--optimize` flag that runs backtest across parameter space and reports best configuration.

**Why:** TrendFollowing has 11 tunable parameters with arbitrary defaults (SMA=50/200, RSI=50-70, stop=5%, take=15%). These weren't optimized for SPY or any specific market. Optimization could significantly improve performance. Industry standard practice for algorithmic strategies.

**Pros:**
- Find parameters that actually work for target symbol/timeframe
- Avoid overfitting by validating on out-of-sample data (once Stage 2 exists)
- Makes TrendFollowing a serious contender vs Buy & Hold
- Learn which parameters matter most (sensitivity analysis)

**Cons:**
- Computationally expensive (grid search of 11 params = millions of combinations)
- Risk of overfitting to historical data (curve fitting)
- Requires careful train/test split to validate properly
- Large effort: human: 1 week / CC: 3-4 hours

**Context:** TrendFollowing currently uses default params from common TA literature (50/200 SMA, 14-period RSI). These may not be optimal for equity indices like SPY. Optimization belongs in a future validation stage (Stage 6?). Start with grid search over 2-3 key params (SMA periods, stop loss %), then expand. Use walk-forward analysis to avoid overfitting. Consider scipy.optimize or optuna library.

**Depends on:** Stage 2 (out-of-sample validation) should exist first to properly validate optimized params

---

## Completed

**v0.0.1 (2026-03-20)** - Stage 1: Basic Metrics Comparison
- CAGR
- Max Drawdown
- Sharpe Ratio
- Calmar Ratio
- Partial: Consistencia (win rate, volatility implemented; drawdown duration pending)
