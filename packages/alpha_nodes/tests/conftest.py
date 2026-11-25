"""Shared fixtures: valid canonical frames for the alpha_nodes datasets."""

import pandas as pd
import pytest


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
