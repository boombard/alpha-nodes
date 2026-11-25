"""Shared fixtures: valid canonical frames for the alpha_nodes datasets, and the offline yfinance replay."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest
import yfinance as yf
from alpha_nodes.providers.yfinance.history import YFHistoryPayload
from lensgraph.sources import FakeClock

if TYPE_CHECKING:
    from .yf_replay import YFReplay

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


@pytest.fixture
def random_walk() -> Callable[[int, int], np.ndarray]:
    """Factory for seeded positive random-walk price arrays: `random_walk(n, seed)`."""

    def make(n: int = 500, seed: int = 0) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))

    return make


@pytest.fixture
def replay(monkeypatch: pytest.MonkeyPatch) -> Iterator["YFReplay"]:
    """`yfinance.Ticker` replaced by the recorded fixtures (see yf_replay.py)."""
    from .yf_replay import YFReplay

    stub = YFReplay()
    stub.install(monkeypatch)
    saved = (yf.config.debug.hide_exceptions, yf.config.network.retries)  # the provider sets these
    yield stub
    yf.config.debug.hide_exceptions, yf.config.network.retries = saved


@pytest.fixture
def clock() -> FakeClock:
    """A Wednesday during LSE trading hours, the day after the fixtures' last bar."""
    return FakeClock(datetime(2026, 11, 25, 10, 0, tzinfo=UTC))


@pytest.fixture
def fundamentals_frame() -> pd.DataFrame:
    """Two annual periods in GBP; the older one has no filing date (yfinance-style) and sparse items."""
    nan = float("nan")
    return pd.DataFrame(
        {
            "period_type": ["annual", "annual"],
            "period_end": pd.to_datetime(["2023-12-31", "2024-12-31"]),
            "filed_at": pd.to_datetime([None, "2025-03-01"]),
            "currency": ["GBP", "GBP"],
            "revenue": [1000.0, 1100.0],
            "operating_income": [100.0, 120.0],
            "net_income": [80.0, 90.0],
            "interest_expense": [nan, 5.0],
            "depreciation_amortization": [20.0, 22.0],
            "operating_cash_flow": [110.0, 130.0],
            "capex": [30.0, 35.0],
            "total_assets": [2000.0, 2100.0],
            "total_liabilities": [1200.0, 1250.0],
            "total_equity": [800.0, 850.0],
            "common_equity": [790.0, 840.0],
            "total_debt": [300.0, 310.0],
            "cash": [150.0, 170.0],
            "shares_diluted": [100.0, 99.0],
            "shares_outstanding": [100.0, 98.0],
        }
    )


@pytest.fixture
def news_frame() -> pd.DataFrame:
    """Two news items; the second has no optional text."""
    return pd.DataFrame(
        {
            "id": ["a1", "a2"],
            "published_at": pd.to_datetime(["2026-01-05T09:00:00Z", "2026-01-06T10:30:00Z"], utc=True).as_unit("ns"),
            "headline": ["Profit up", "CEO steps down"],
            "source": ["Wire", None],
            "url": ["https://example.test/a1", None],
            "summary": ["Profits rose.", None],
        }
    )
