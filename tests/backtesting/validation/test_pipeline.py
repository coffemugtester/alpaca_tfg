"""Unit tests for ValidationPipeline CSV export helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from backtesting.validation.pipeline import ValidationPipeline


class _FakeAnalyzer:
    def __init__(self, payload):
        self._payload = payload

    def get_analysis(self):
        return self._payload


def _build_pipeline() -> ValidationPipeline:
    return ValidationPipeline(
        strategies={},
        symbol="SPY",
        start=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end=datetime(2023, 1, 10, tzinfo=timezone.utc),
        cash=10_000.0,
        commission=0.0,
        slippage=0.0,
    )


def _build_result(strategy_name: str, daily_account_data: dict) -> dict:
    analyzers = SimpleNamespace(
        daily_account=_FakeAnalyzer(daily_account_data),
    )
    strategy_instance = SimpleNamespace(analyzers=analyzers)
    cerebro = SimpleNamespace(runstrats=[[strategy_instance]])
    return {
        "strategy_name": strategy_name,
        "cerebro": cerebro,
        "initial_cash": 10_000.0,
    }


def test_extract_daily_exposure_rows_long_format_schema():
    pipeline = _build_pipeline()
    d1 = datetime(2023, 1, 2, tzinfo=timezone.utc)
    d2 = datetime(2023, 1, 3, tzinfo=timezone.utc)
    result = _build_result(
        strategy_name="DCA",
        daily_account_data={
            d1: {"portfolio_value": 11000.0, "available_cash": 4000.0},
            d2: {"portfolio_value": 11000.0, "available_cash": 3000.0},
        },
    )

    rows = pipeline._extract_daily_exposure_rows(result)

    assert len(rows) == 2
    assert list(rows[0].keys()) == [
        "date",
        "strategy",
        "portfolio_value",
        "available_cash",
        "exposure",
        "cash_pct",
        "exposure_pct",
    ]
    assert rows[0]["strategy"] == "DCA"
    assert rows[0]["date"] == "2023-01-02"
    assert rows[0]["portfolio_value"] == 11000.0
    assert rows[0]["available_cash"] == 4000.0
    assert rows[0]["exposure"] == 7000.0
    assert 0.0 <= rows[0]["cash_pct"] <= 1.0
    assert 0.0 <= rows[0]["exposure_pct"] <= 1.0


def test_export_daily_exposure_csv_writes_file_and_skips_failed(monkeypatch, tmp_path):
    pipeline = _build_pipeline()
    d1 = datetime(2023, 1, 2, tzinfo=timezone.utc)
    d2 = datetime(2023, 1, 3, tzinfo=timezone.utc)

    valid_result = _build_result(
        strategy_name="Buy & Hold",
        daily_account_data={
            d1: {"portfolio_value": 10200.0, "available_cash": 500.0},
            d2: {"portfolio_value": 10098.0, "available_cash": 500.0},
        },
    )
    failed_result = {"strategy_name": "TrendFollowing", "error": "failed run"}

    monkeypatch.chdir(tmp_path)
    pipeline._export_daily_exposure_csv([valid_result, failed_result])

    matches = sorted(Path(tmp_path).glob("comparison_exposure_SPY_*.csv"))
    assert len(matches) == 1

    content = matches[0].read_text(encoding="utf-8")
    assert "date,strategy,portfolio_value,available_cash,exposure,cash_pct,exposure_pct" in content
    assert "Buy & Hold" in content
    assert "TrendFollowing" not in content
