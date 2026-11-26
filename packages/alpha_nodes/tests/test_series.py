"""Tests for the price frame adapters (`alpha_nodes.series`)."""

from collections.abc import Callable
from datetime import date

import pandas as pd
import pytest
from alpha_nodes.providers.yfinance.history import YFHistoryPayload, normalise_prices
from alpha_nodes.series import (
    TotalReturnSchema,
    bars_back,
    close_on,
    total_return,
    trailing,
    window_info,
)

Loader = Callable[[str], YFHistoryPayload]


def _prices(
    close: list[float], dividends: list[float] | None = None, quality: list[str] | None = None
) -> pd.DataFrame:
    n = len(close)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-05", periods=n),
            "close": close,
            "dividends": dividends or [0.0] * n,
            "quality": quality or ["ok"] * n,
            "currency": "GBP",
        }
    )


def test_total_return_applies_dividend_on_ex_date() -> None:
    frame = total_return(_prices([100.0, 100.0, 90.0], [0.0, 0.0, 10.0]))
    assert frame["tr_index"].tolist() == pytest.approx([1.0, 1.0, 1.0])  # 90 + 10 == 100
    TotalReturnSchema.validate(frame)


def test_total_return_rejects_duplicate_dates() -> None:
    prices = _prices([100.0, 101.0])
    prices.loc[1, "date"] = prices.loc[0, "date"]
    with pytest.raises(ValueError, match="duplicate"):
        total_return(prices)


def test_total_return_sorts_by_date() -> None:
    frame = total_return(_prices([100.0, 110.0, 121.0]).iloc[::-1])
    assert frame["date"].is_monotonic_increasing
    assert frame["tr_index"].tolist() == pytest.approx([1.0, 1.1, 1.21])


def test_suspect_flag_from_quality() -> None:
    frame = total_return(_prices([100.0, 101.0, 102.0], quality=["ok", "suspect", "ok"]))
    assert frame["suspect"].tolist() == [False, True, False]


def test_trailing_and_window_info() -> None:
    frame = total_return(_prices([100.0 + i for i in range(10)], quality=["suspect"] + ["ok"] * 9))
    tail = trailing(frame, 4)
    assert len(tail) == 4
    assert len(trailing(frame, 50)) == 10
    info = window_info(tail)
    assert (info.bars, info.suspect_bars, info.currency) == (4, 0, "GBP")
    assert info.start == tail["date"].iloc[0].date()
    assert info.end == frame["date"].iloc[-1].date()
    assert window_info(frame).suspect_bars == 1


def test_empty_prices_give_empty_frame() -> None:
    empty = _prices([]).astype({"date": "datetime64[ns]"})
    frame = total_return(empty)
    assert frame.empty
    assert list(frame.columns) == ["date", "close", "dividends", "tr_index", "suspect", "currency"]
    TotalReturnSchema.validate(frame)
    info = window_info(frame)
    assert (info.bars, info.start, info.end, info.suspect_bars, info.currency) == (0, None, None, 0, None)


def test_dividends_on_split_basis_on_aapl_fixture(yf_payload: Loader) -> None:
    """Closes are split-adjusted through the 4:1 split, and AAPL's dividends sit on the same basis."""
    split = total_return(normalise_prices(yf_payload("split_AAPL"), "XNYS"))
    on_split = split["date"] == pd.Timestamp("2020-08-31")
    jump = float(split["tr_index"].pct_change().to_numpy()[on_split.to_numpy()][0])
    assert abs(jump) < 0.05  # no 4x artefact on the split date
    # The split window holds no dividend, so the basis is read from the two-year fixture:
    # every payout is within 10% of its neighbours (no 4x step), the same basis as its closes.
    frame = normalise_prices(yf_payload("prices_AAPL"), "XNYS")
    paid = frame["dividends"].to_numpy()
    paid = paid[paid > 0]
    assert len(paid) >= 4
    assert paid.max() / paid.min() < 1.1
    # Level check: a x4 basis error would push the trailing-year yield out of this range.
    last = frame["date"].iloc[-1]
    year = frame["dividends"].to_numpy()[(frame["date"] > last - pd.DateOffset(years=1)).to_numpy()]
    assert 0.002 < year.sum() / frame["close"].iloc[-1] < 0.015


def test_close_on_takes_last_bar_on_or_before() -> None:
    prices = _prices([10.0, 11.0, 12.0]).assign(currency="GBP")  # Mon 5, Tue 6, Wed 7 Jan 2026
    assert close_on(prices, date(2026, 1, 6)) == (date(2026, 1, 6), 11.0, "GBP")
    assert close_on(prices, date(2026, 1, 10)) == (date(2026, 1, 7), 12.0, "GBP")  # Saturday


def test_close_on_none_before_first_bar() -> None:
    prices = _prices([10.0]).assign(currency="GBP")
    assert close_on(prices, date(2026, 1, 4)) is None
    assert close_on(prices.iloc[0:0], date(2026, 1, 4)) is None


def test_bars_back() -> None:
    prices = _prices([1.0, 2.0, 3.0, 4.0])  # 5, 6, 7, 8 Jan 2026
    assert bars_back(prices, date(2026, 1, 8), 2) == date(2026, 1, 6)
    assert bars_back(prices, date(2026, 1, 10), 3) == date(2026, 1, 5)  # counts from the last bar on or before
    assert bars_back(prices, date(2026, 1, 8), 4) is None  # history too short
    assert bars_back(prices, date(2026, 1, 1), 0) is None  # no bar yet
