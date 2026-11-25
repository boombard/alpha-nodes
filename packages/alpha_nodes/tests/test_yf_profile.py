"""yfinance profile: normalisation from recorded fixtures, provider fetch, canary comparison."""

import importlib.util
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import yfinance as yf
import yfinance.cache as yf_cache
from alpha_nodes import datasets
from alpha_nodes.datasets import PROFILE, ProfileSchema
from alpha_nodes.providers.yfinance import provider as provider_mod
from alpha_nodes.providers.yfinance.history import YFHistoryPayload, normalise_prices
from alpha_nodes.providers.yfinance.profile import YFProfilePayload, normalise_profile
from alpha_nodes.providers.yfinance.provider import YFinanceProvider, symbol_mic
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from lensgraph.sources import FakeClock, NormalisedMeta, RawResponse, WorkItem
from yfinance.exceptions import YFRateLimitError

from .conftest import YF_FIXTURES

SYMBOLS = [
    "BP.L",
    "HSBA.L",
    "VOD.L",
    "ASML.AS",
    "SAP.DE",
    "NESN.SW",
    "NOVO-B.CO",
    "AAPL",
    "VUSD.L",
    "BOOT.L",
    "ALCLS.PA",
]
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def load(symbol: str) -> YFProfilePayload:
    """A fresh copy of the recorded profile payload, safe to mutate into a variant."""
    return YFProfilePayload.model_validate_json(
        (YF_FIXTURES / f"profile_{symbol}.json").read_text()
    )


def norm(payload: YFProfilePayload) -> pd.DataFrame:
    return normalise_profile(payload, symbol_mic(payload.symbol))


def _canary() -> Any:
    path = Path(__file__).parents[1] / "scripts" / "canary.py"
    spec = importlib.util.spec_from_file_location("canary", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bp_reports_usd_trades_gbp() -> None:
    payload = load("BP.L")
    assert payload.info["currency"] == "GBp"
    row = norm(payload).iloc[0]
    assert row["trading_currency"] == "GBP"
    assert row["reporting_currency"] == "USD"
    assert row["repairs"] == ["minor_unit"]
    assert row["quality"] == "ok"  # differing currencies are normal, not suspect
    assert row["exchange"] == "XLON"


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_profile_validates_for_every_fixture(symbol: str) -> None:
    frame = norm(load(symbol))
    assert len(frame) == 1
    ProfileSchema.validate(frame)
    NormalisedMeta.validate(frame)
    assert frame["quality"].iloc[0] != "rejected"


def test_dual_listing_has_isin() -> None:
    """AAPL's fixture is the one whose Yahoo `isin` came back well-formed (most are "-")."""
    assert norm(load("AAPL"))["isin"].iloc[0] == "US0378331005"
    assert norm(load("BP.L"))["isin"].iloc[0] is None


def test_listing_date_and_text_fields_mapped() -> None:
    payload = load("BP.L")
    row = norm(payload).iloc[0]
    assert row["listing_date"] == pd.Timestamp("1988-06-30") or row["listing_date"].year == 1988
    assert row["name"] == payload.info["longName"]
    assert row["sector"] == payload.info["sector"]
    assert row["business_summary"] == payload.info["longBusinessSummary"]
    assert row["shares_outstanding"] == payload.info["sharesOutstanding"]


def test_no_yahoo_ratios_ingested() -> None:
    frame = norm(load("BP.L"))
    expected = {*ProfileSchema.to_schema().columns, "repairs", "quality", "quality_reasons"}
    assert set(frame.columns) == {*expected, "known_at"}
    assert "marketCap" not in frame.columns


@pytest.mark.parametrize("bad", [None, 0, -5])
def test_missing_shares_marked_suspect(bad: int | None) -> None:
    payload = load("BP.L")
    if bad is None:
        del payload.info["sharesOutstanding"]
    else:
        payload.info["sharesOutstanding"] = bad
    row = norm(payload).iloc[0]
    assert row["quality"] == "suspect"
    assert row["quality_reasons"] == ["no_shares"]
    assert pd.isna(row["shares_outstanding"])
    ProfileSchema.validate(norm(payload))


def test_etf_fixture_without_shares_is_suspect() -> None:
    assert norm(load("VUSD.L"))["quality"].iloc[0] == "suspect"


def test_missing_name_rejected_and_short_name_is_fallback() -> None:
    payload = load("BP.L")
    short = payload.info["longName"]
    payload.info["shortName"] = short
    del payload.info["longName"]
    assert norm(payload)["name"].iloc[0] == short
    del payload.info["shortName"]
    row = norm(payload).iloc[0]
    assert row["quality"] == "rejected"


def test_valid_isin_kept_and_corrupted_check_digit_dropped() -> None:
    valid = norm(load("AAPL")).iloc[0]
    assert valid["isin"] == "US0378331005"
    assert valid["quality"] == "ok"
    bad = load("AAPL")
    bad.isin = "US0378331006"  # check digit corrupted
    row = norm(bad).iloc[0]
    assert row["isin"] is None
    assert row["quality"] == "suspect"
    assert row["quality_reasons"] == ["bad_isin"]
    bad.isin = "NOTANISIN"  # wrong shape
    assert norm(bad).iloc[0]["quality_reasons"] == ["bad_isin"]


def test_missing_trading_currency_raises() -> None:
    payload = load("BP.L")
    del payload.info["currency"]
    with pytest.raises(ValueError, match="BP.L"):
        norm(payload)


# --- provider -------------------------------------------------------------------------------


class InfoStub:
    """Replacement for `yfinance.Ticker` serving `.info` and `.isin` or raising."""

    def __init__(self) -> None:
        self.answers: dict[str, YFProfilePayload | Exception] = {}

    def __call__(self, symbol: str) -> Any:
        answer = self.answers[symbol]

        class _T:
            @property
            def info(self) -> dict[str, Any]:
                if isinstance(answer, Exception):
                    raise answer
                return answer.info

            @property
            def isin(self) -> str:
                assert isinstance(answer, YFProfilePayload)
                return answer.isin or "-"

        return _T()


@pytest.fixture
def info_stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[InfoStub]:
    stub = InfoStub()
    monkeypatch.setattr(provider_mod.yf, "Ticker", stub)
    monkeypatch.setattr(yf_cache, "set_cache_location", lambda _dir: None)
    saved = (yf.config.debug.hide_exceptions, yf.config.network.retries)
    yield stub
    yf.config.debug.hide_exceptions, yf.config.network.retries = saved


@pytest.fixture
def provider(info_stub: InfoStub, tmp_path: Path) -> YFinanceProvider:
    return YFinanceProvider(tmp_path, FakeClock(NOW))


def _fetch(provider: YFinanceProvider, symbol: str):
    (outcome,) = provider.fetch(
        PROFILE, [WorkItem(dataset="profile", entity=symbol, interval=None)]
    )
    return outcome


def test_profile_in_capabilities_and_fetch_outcomes_classified(
    provider: YFinanceProvider, info_stub: InfoStub
) -> None:
    assert "profile" in provider.capabilities.datasets
    assert provider.capabilities.pit_reliable["profile"] is False
    assert provider.normaliser_version("profile")

    info_stub.answers["BP.L"] = load("BP.L")
    ok = _fetch(provider, "BP.L")
    assert ok.kind == "ok"
    assert ok.settled_through is None
    assert YFProfilePayload.model_validate(ok.payload) == load("BP.L")

    not_found = CurlHTTPError("HTTP Error 404: ")
    not_found.response = SimpleNamespace(status_code=404)  # type: ignore[assignment]
    cases: list[tuple[Exception, str]] = [
        (YFRateLimitError(), "rate_limited"),
        (not_found, "empty"),
        (CurlConnectionError("down"), "unreachable"),
        (RuntimeError("boom"), "error"),
    ]
    for exc, kind in cases:
        info_stub.answers["X.L"] = exc
        assert _fetch(provider, "X.L").kind == kind

    empty = load("BP.L").model_copy(update={"info": {}})
    info_stub.answers["X.L"] = empty
    assert _fetch(provider, "X.L").kind == "empty"


def test_stub_info_for_unknown_symbol_is_empty(
    provider: YFinanceProvider, info_stub: InfoStub
) -> None:
    """Yahoo answers `.info` for an unknown symbol with a non-empty stub, not {}."""
    info_stub.answers["GONE.L"] = YFProfilePayload(
        symbol="GONE.L", info={"trailingPegRatio": None}, isin=None
    )
    outcome = _fetch(provider, "GONE.L")
    assert outcome.kind == "empty"
    assert "no currency" in (outcome.message or "")


def test_unrecognised_currency_in_info_is_error(
    provider: YFinanceProvider, info_stub: InfoStub
) -> None:
    info_stub.answers["ODD.L"] = YFProfilePayload(
        symbol="ODD.L", info={"currency": "pounds", "longName": "Odd plc"}, isin=None
    )
    outcome = _fetch(provider, "ODD.L")
    assert outcome.kind == "error"
    assert "pounds" in (outcome.message or "")


def test_provider_normalise_profile_accepts_stored_dict(provider: YFinanceProvider) -> None:
    payload = load("BP.L")
    raw = RawResponse(
        raw_id="r1",
        provider="yfinance",
        dataset="profile",
        entity="BP.L",
        interval=None,
        payload_hash="h",
        fetched_at=NOW,
        library_version="1.8.0",
    )
    frame = provider.normalise(datasets.PROFILE, raw, payload.model_dump(mode="json"))
    assert frame["trading_currency"].iloc[0] == "GBP"


# --- canary comparison ------------------------------------------------------------------------


@pytest.fixture
def fixture_frame(yf_payload: Callable[[str], YFHistoryPayload]) -> pd.DataFrame:
    return normalise_prices(yf_payload("prices_BP.L"), "XLON")


def test_canary_compare_clean_when_equal(fixture_frame: pd.DataFrame) -> None:
    assert _canary().compare_prices(fixture_frame, fixture_frame.copy()) == []


def test_canary_compare_flags_unit_drift(fixture_frame: pd.DataFrame) -> None:
    scaled = fixture_frame.copy()
    for col in ("open", "high", "low", "close"):
        scaled[col] = scaled[col] * 100
    problems = _canary().compare_prices(fixture_frame, scaled)
    assert any("close" in p for p in problems)


def test_canary_compare_flags_currency_and_repairs(fixture_frame: pd.DataFrame) -> None:
    live = fixture_frame.copy()
    live["currency"] = "USD"
    live["repairs"] = [[] for _ in range(len(live))]
    problems = " | ".join(_canary().compare_prices(fixture_frame, live))
    assert "currency" in problems
    assert "repairs" in problems


def test_canary_compare_flags_dtype_and_column_changes(fixture_frame: pd.DataFrame) -> None:
    live = fixture_frame.copy()
    live["volume"] = live["volume"].astype(float)
    assert any("dtype of volume" in p for p in _canary().compare_prices(fixture_frame, live))
    assert any(
        "columns" in p for p in _canary().compare_prices(fixture_frame, live.drop(columns="open"))
    )


def test_canary_compare_profile_currencies() -> None:
    old = norm(load("BP.L"))
    assert _canary().compare_profile(old, old.copy()) == []
    new = old.copy()
    new["reporting_currency"] = "EUR"
    assert any("reporting_currency" in p for p in _canary().compare_profile(old, new))
