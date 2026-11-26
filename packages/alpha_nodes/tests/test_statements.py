"""Tests for the fundamentals frame adapters (`alpha_nodes.statements`)."""

from collections.abc import Callable
from datetime import date

import pandas as pd
import pytest
from alpha_nodes.conventions import MAX_ANNUAL_PERIODS
from alpha_nodes.money import CurrencyMismatch
from alpha_nodes.statements import (
    AnnualFundamentalsSchema,
    annual_periods,
    known_on,
    period_window,
    values,
)

Rows = Callable[..., pd.DataFrame]


def test_known_on_uses_filed_at(fundamentals_rows: Rows) -> None:
    frame = fundamentals_rows(
        {"period_end": "2022-12-31", "filed_at": "2023-03-01"},
        {"period_end": "2023-12-31", "filed_at": "2024-03-01"},
    )
    assert known_on(frame, date(2023, 6, 1))["period_end"].tolist() == [pd.Timestamp("2022-12-31")]
    assert len(known_on(frame, date(2024, 3, 1))) == 2  # filed on the day counts


def test_known_on_applies_filing_lag_without_filed_at(fundamentals_rows: Rows) -> None:
    frame = fundamentals_rows({"period_end": "2023-12-31"})  # +90 days = 2024-03-30
    assert known_on(frame, date(2024, 3, 29)).empty
    assert len(known_on(frame, date(2024, 3, 30))) == 1


def test_annual_periods_takes_latest_filing_known_then(fundamentals_rows: Rows) -> None:
    frame = fundamentals_rows(
        {"period_end": "2023-12-31", "filed_at": "2024-03-01", "revenue": 100.0},
        {"period_end": "2023-12-31", "filed_at": "2025-03-01", "revenue": 120.0},  # restatement
    )
    assert annual_periods(frame, date(2024, 6, 1))["revenue"].tolist() == [100.0]
    assert annual_periods(frame, date(2025, 3, 1))["revenue"].tolist() == [120.0]


def test_annual_periods_treats_null_filed_at_as_oldest(fundamentals_rows: Rows) -> None:
    frame = fundamentals_rows(
        {"period_end": "2022-12-31", "revenue": 1.0},
        {"period_end": "2022-12-31", "filed_at": "2023-03-01", "revenue": 2.0},
    )
    assert annual_periods(frame, date(2024, 1, 1))["revenue"].tolist() == [2.0]


def test_annual_periods_caps_and_sorts(fundamentals_rows: Rows) -> None:
    years = [
        2030,
        2012,
        2025,
        2015,
        2020,
        2013,
        2014,
        2016,
        2017,
        2018,
        2019,
        2021,
        2022,
        2023,
        2024,
    ]
    frame = fundamentals_rows(*({"period_end": f"{y}-12-31"} for y in years))
    out = annual_periods(frame, date(2031, 12, 31))
    assert [d.year for d in out["period_end"]] == [*range(2017, 2026), 2030]
    assert len(out) == MAX_ANNUAL_PERIODS
    three = annual_periods(frame, date(2031, 12, 31), max_periods=3)
    assert [d.year for d in three["period_end"]] == [2024, 2025, 2030]
    AnnualFundamentalsSchema.validate(out)


def test_currency_change_raises(fundamentals_rows: Rows) -> None:
    frame = fundamentals_rows(
        {"period_end": "2021-12-31", "currency": "GBP"},
        {"period_end": "2022-12-31", "currency": "USD"},
    )
    with pytest.raises(CurrencyMismatch):
        annual_periods(frame, date(2024, 1, 1))


def test_suspect_from_quality(fundamentals_rows: Rows) -> None:
    frame = fundamentals_rows(
        {"period_end": "2021-12-31", "quality": "ok"},
        {"period_end": "2022-12-31", "quality": "suspect"},
    )
    assert annual_periods(frame, date(2024, 1, 1))["suspect"].tolist() == [False, True]


def test_empty_frame_keeps_columns(fundamentals_rows: Rows) -> None:
    out = annual_periods(fundamentals_rows(), date(2024, 1, 1))
    assert out.empty
    assert list(out.columns) == list(AnnualFundamentalsSchema.to_schema().columns)
    AnnualFundamentalsSchema.validate(out)
    assert period_window(out).periods == 0


def test_values_drops_periods_missing_a_column(fundamentals_rows: Rows) -> None:
    frame = fundamentals_rows(
        {"period_end": "2020-12-31", "revenue": 1.0, "net_income": 1.0},
        {"period_end": "2021-12-31", "revenue": 2.0},
        {"period_end": "2022-12-31", "revenue": 3.0, "net_income": 3.0, "quality": "suspect"},
    )
    used, window = values(annual_periods(frame, date(2024, 1, 1)), "revenue", "net_income")
    assert used["revenue"].tolist() == [1.0, 3.0]
    assert (window.periods, window.suspect_periods, window.currency) == (2, 1, "GBP")
    assert (window.first_period_end, window.last_period_end) == (
        date(2020, 12, 31),
        date(2022, 12, 31),
    )
