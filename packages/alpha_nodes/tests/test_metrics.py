from datetime import date

import pytest
from alpha_nodes.metrics import (
    DrawdownResult,
    MomentumResult,
    PriceWindow,
    TrendResult,
    VolatilityResult,
)
from pydantic import ValidationError


def test_suspect_bars_cannot_exceed_bars():
    with pytest.raises(ValidationError, match="suspect_bars"):
        PriceWindow(bars=2, start=date(2024, 1, 1), end=date(2024, 1, 2), suspect_bars=3)


def test_results_are_frozen():
    result = MomentumResult(bars=0, start=None, end=None, suspect_bars=0, total_return=None)
    with pytest.raises(ValidationError):
        result.bars = 1  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValidationError):
        MomentumResult(bars=0, start=None, end=None, suspect_bars=0, total_return=None, junk=1)  # pyright: ignore[reportCallIssue]


def test_none_fields_allowed_for_short_history():
    empty = {"bars": 0, "start": None, "end": None, "suspect_bars": 0}
    assert TrendResult(**empty, close=None, ma=None, pct_above_ma=None, ma_slope=None).ma is None
    assert VolatilityResult(**empty, annualised=None).annualised is None
    dd = DrawdownResult(**empty, max_drawdown=None, peak_date=None, trough_date=None)
    assert dd.trough_date is None
