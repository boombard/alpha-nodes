"""Shared fixtures: valid canonical frames for the alpha_nodes datasets."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from alpha_nodes.providers.yfinance.history import YFHistoryPayload

YF_FIXTURES = Path(__file__).parent / "fixtures" / "yfinance"


@pytest.fixture
def prices_frame() -> pd.DataFrame:
    """Two valid trading days of GBP prices."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": pd.array([1000, None], dtype="Int64"),
            "dividends": [0.0, 0.5],
            "split_ratio": [1.0, 1.0],
            "currency": ["GBP", "GBP"],
        }
    )


@pytest.fixture
def profile_frame() -> pd.DataFrame:
    """One profile row with every optional field missing."""
    return pd.DataFrame(
        {
            "name": ["HSBC Holdings"],
            "isin": [None],
            "exchange": ["XLON"],
            "country": [None],
            "trading_currency": ["GBP"],
            "reporting_currency": [None],
            "sector": [None],
            "industry": [None],
            "shares_outstanding": pd.array([None], dtype="float64"),
            "listing_date": pd.to_datetime([None]),
            "business_summary": [None],
        }
    )


@pytest.fixture
def fx_frame() -> pd.DataFrame:
    """One valid FX row."""
    return pd.DataFrame({"date": pd.to_datetime(["2026-01-05"]), "usd_per_unit": [1.27]})


@pytest.fixture
def yf_payload() -> Callable[[str], YFHistoryPayload]:
    """Loader for a recorded yfinance chart payload by file stem, e.g. `prices_BP.L`.

    Returns a fresh copy each call, so tests may mutate it into a constructed variant.
    """

    def load(name: str) -> YFHistoryPayload:
        return YFHistoryPayload.model_validate_json((YF_FIXTURES / f"{name}.json").read_text())

    return load


def yf_frame(payload: YFHistoryPayload) -> pd.DataFrame:
    """Rebuild the `Ticker.history` frame (tz-aware index) that a payload was captured from."""
    frame = pd.DataFrame(payload.data, columns=payload.columns, dtype=float)
    tz = payload.metadata.get("exchangeTimezoneName", "UTC")
    frame.index = pd.DatetimeIndex(pd.to_datetime(payload.index, utc=True), name="Date").tz_convert(
        tz
    )
    return frame
