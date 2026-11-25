"""YFinanceProvider with `yfinance.Ticker` replaced by a stub serving the recorded fixtures."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import yfinance as yf
import yfinance._http as yf_http
import yfinance.cache as yf_cache
from alpha_nodes import datasets, markets
from alpha_nodes.providers.yfinance import provider as provider_mod
from alpha_nodes.providers.yfinance.history import YFHistoryPayload
from alpha_nodes.providers.yfinance.provider import (
    YF_POLICY,
    YFinanceProvider,
    fx_symbol,
    symbol_mic,
)
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from curl_cffi.requests.exceptions import Timeout as CurlTimeout
from lensgraph.sources import (
    DateInterval,
    FakeClock,
    RawResponse,
    WorkItem,
)
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError, YFTzMissingError

from .conftest import yf_frame

Loader = Callable[[str], YFHistoryPayload]
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)  # after the LSE close... see tests for overrides


class YFStub:
    """Replacement for `yfinance.Ticker`: serves payload frames or raises, and logs calls."""

    def __init__(self) -> None:
        self.answers: dict[str, YFHistoryPayload | Exception] = {}
        self.calls: list[dict[str, Any]] = []
        self.known_tz: dict[str, str] = {}

    def __call__(self, symbol: str) -> "_StubTicker":
        return _StubTicker(self, symbol)


class _StubTicker:
    def __init__(self, stub: YFStub, symbol: str) -> None:
        self.stub, self.symbol = stub, symbol

    def history(self, *, start: date, end: date, **kwargs: Any) -> pd.DataFrame:
        self.stub.calls.append({"symbol": self.symbol, "start": start, "end": end, **kwargs})
        answer = self.stub.answers[self.symbol]
        if isinstance(answer, Exception):
            raise answer
        frame = yf_frame(answer)
        days = pd.Index([ts.date() for ts in frame.index])
        return pd.DataFrame(frame[(days >= start) & (days < end)])

    @property
    def history_metadata(self) -> dict[str, Any]:
        answer = self.stub.answers[self.symbol]
        assert isinstance(answer, YFHistoryPayload)
        return answer.metadata


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[YFStub]:
    """Stub `yfinance.Ticker`, the cache location and the timezone lookup; no network."""
    stub = YFStub()
    monkeypatch.setattr(provider_mod.yf, "Ticker", stub)
    monkeypatch.setattr(yf_cache, "set_cache_location", lambda _dir: None)
    monkeypatch.setattr(provider_mod, "_known_timezone", lambda sym: stub.known_tz.get(sym))
    saved = (yf.config.debug.hide_exceptions, yf.config.network.retries)  # provider sets these
    yield stub
    yf.config.debug.hide_exceptions, yf.config.network.retries = saved


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def provider(stub: YFStub, clock: FakeClock, tmp_path: Path) -> YFinanceProvider:
    return YFinanceProvider(tmp_path, clock)


def _http_error(status: int) -> CurlHTTPError:
    """The error curl_cffi raises for an HTTP status, as recorded in probe_http_404.json."""
    error = CurlHTTPError(f"HTTP Error {status}: ")
    error.response = SimpleNamespace(status_code=status)  # type: ignore[assignment]
    return error


def _item(entity: str, start: date, end: date, dataset: str = "prices") -> WorkItem:
    return WorkItem(dataset=dataset, entity=entity, interval=DateInterval(start=start, end=end))


def _fetch(provider: YFinanceProvider, item: WorkItem):
    dataset = datasets.DATASETS[item.dataset]
    (outcome,) = provider.fetch(dataset, [item])
    return outcome


def _raw(item: WorkItem) -> RawResponse:
    return RawResponse(
        raw_id="r1",
        provider="yfinance",
        dataset=item.dataset,
        entity=item.entity,
        interval=item.interval,
        payload_hash="h",
        fetched_at=NOW,
        library_version="1.8.0",
    )


def test_symbol_mic_and_fx_symbol() -> None:
    assert symbol_mic("BP.L") == "XLON"
    assert symbol_mic("NOVO-B.CO") == "XCSE"
    assert symbol_mic("AAPL") == "XNYS"
    assert fx_symbol("GBP") == "GBPUSD=X"
    with pytest.raises(ValueError, match=r"\.ZZ"):
        symbol_mic("FOO.ZZ")


def test_capabilities_declared(provider: YFinanceProvider) -> None:
    caps = provider.capabilities
    assert provider.name == "yfinance"
    assert caps.datasets == {"prices", "fx", "profile"}
    assert caps.max_batch == 1
    assert caps.rate_limit == YF_POLICY
    assert caps.pit_reliable == {"prices": True, "fx": True, "profile": False}
    assert (YF_POLICY.concurrency, YF_POLICY.per_second, YF_POLICY.burst) == (4, 2, 4)
    assert YF_POLICY.backoff_s == (30, 60, 120, 240)
    assert provider.library_version == yf.__version__


def test_setup_configures_yfinance(
    stub: YFStub, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(yf_cache, "set_cache_location", seen.append)
    YFinanceProvider(tmp_path, clock)
    assert seen == [str(tmp_path)]
    assert yf.config.debug.hide_exceptions is False
    assert yf.config.network.retries == 2


def test_missing_curl_cffi_raises(
    stub: YFStub, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(yf_http, "HAS_CURL_CFFI", False)
    with pytest.raises(RuntimeError, match="curl_cffi"):
        YFinanceProvider(tmp_path, clock)


@pytest.mark.parametrize(
    ("error", "tz", "kind", "settled"),
    [
        (YFRateLimitError(), None, "rate_limited", False),
        (YFTzMissingError("X.L"), None, "empty", False),
        (YFPricesMissingError("X.L", ""), None, "empty", False),
        (YFPricesMissingError("X.L", ""), "Europe/London", "ok", True),
        (_http_error(404), None, "empty", False),
        (_http_error(500), None, "error", False),
        (CurlConnectionError("down"), None, "unreachable", False),
        (CurlTimeout("slow"), None, "unreachable", False),
        (TimeoutError("slow"), None, "unreachable", False),
        (ValueError("boom"), None, "error", False),
    ],
)
def test_exceptions_classified(
    provider: YFinanceProvider,
    stub: YFStub,
    error: Exception,
    tz: str | None,
    kind: str,
    settled: bool,
) -> None:
    stub.answers["X.L"] = error
    if tz:
        stub.known_tz["X.L"] = tz
    outcome = _fetch(provider, _item("X.L", date(2026, 11, 20), date(2026, 11, 24)))
    assert outcome.kind == kind
    assert (outcome.settled_through is not None) is settled
    if kind == "error":
        assert str(error) in outcome.message
    if kind == "ok":
        assert outcome.payload.data == []  # an empty interval, not an empty entity
        frame = provider.normalise(datasets.PRICES, _raw(outcome.item), outcome.payload)
        assert frame.empty


def test_live_bar_after_settled_cut_not_a_fact(
    provider: YFinanceProvider, stub: YFStub, clock: FakeClock, yf_payload: Loader
) -> None:
    stub.answers["BP.L"] = yf_payload("prices_BP.L")
    clock._now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)  # LSE is open
    outcome = _fetch(provider, _item("BP.L", date(2026, 11, 20), date(2026, 11, 25)))
    assert outcome.kind == "ok"
    assert outcome.settled_through == date(2026, 11, 24)


def test_fx_settled_through_is_previous_utc_day(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    stub.answers["GBPUSD=X"] = yf_payload("fx_GBPUSD=X")
    outcome = _fetch(provider, _item("GBP", date(2026, 11, 1), date(2026, 11, 24), "fx"))
    assert stub.calls[0]["symbol"] == "GBPUSD=X"
    assert outcome.settled_through == date(2026, 11, 24)
    frame = provider.normalise(datasets.FX, _raw(outcome.item), outcome.payload)
    assert bool((frame["usd_per_unit"] > 1).all())


def test_request_padded_for_repair_context(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    stub.answers["ASML.AS"] = yf_payload("prices_ASML.AS")
    day = date(2026, 11, 24)
    outcome = _fetch(provider, _item("ASML.AS", day, day))
    (call,) = stub.calls
    assert call["start"] == day - timedelta(days=183)
    assert call["end"] == day + timedelta(days=1)
    assert call["auto_adjust"] is False and call["actions"] is True and call["repair"] is True
    assert outcome.payload.requested_start == outcome.payload.requested_end == day  # coverage
    assert len(outcome.payload.index) > 100  # the context rows are stored


def test_padding_rows_not_returned(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    stub.answers["ASML.AS"] = yf_payload("prices_ASML.AS")
    start, end = date(2026, 11, 18), date(2026, 11, 24)
    outcome = _fetch(provider, _item("ASML.AS", start, end))
    assert len(outcome.payload.index) > 100  # stored verbatim, padding included
    frame = provider.normalise(datasets.PRICES, _raw(outcome.item), outcome.payload)
    days = [d.date() for d in frame["date"]]
    assert days == markets.sessions("XAMS", start, end)


def test_wide_request_not_padded(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    stub.answers["ASML.AS"] = yf_payload("prices_ASML.AS")
    _fetch(provider, _item("ASML.AS", date(2025, 1, 2), date(2026, 11, 24)))
    assert stub.calls[0]["start"] == date(2025, 1, 2)


def test_jump_on_first_requested_day_caught(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    """Constructed variant: the last ASML close is x100 the session before; a 1-day top-up."""
    payload = yf_payload("prices_ASML.AS")
    payload.data[-1][payload.columns.index("Close")] *= 100  # type: ignore[operator]
    stub.answers["ASML.AS"] = payload
    day = date.fromisoformat(payload.index[-1][:10])
    outcome = _fetch(provider, _item("ASML.AS", day, day))
    frame = provider.normalise(datasets.PRICES, _raw(outcome.item), outcome.payload)
    last = frame.iloc[-1]
    assert last["date"].date() == day
    assert last["quality"] == "suspect"
    assert "jump_x100" in last["quality_reasons"]


def test_split_in_top_up_sets_restated_before(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    stub.answers["AAPL"] = yf_payload("split_AAPL")
    outcome = _fetch(provider, _item("AAPL", date(2020, 8, 28), date(2020, 9, 3)))
    assert outcome.restated_before == date(2020, 8, 31)


def test_split_far_after_requested_start_not_a_restatement(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    """A backfill starting over two years before the split already holds nothing to restate."""
    stub.answers["AAPL"] = yf_payload("split_AAPL")
    outcome = _fetch(provider, _item("AAPL", date(2018, 1, 2), date(2020, 9, 3)))
    assert outcome.restated_before is None


def test_no_split_no_restatement(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    stub.answers["ASML.AS"] = yf_payload("prices_ASML.AS")
    outcome = _fetch(provider, _item("ASML.AS", date(2026, 11, 20), date(2026, 11, 24)))
    assert outcome.restated_before is None


def test_normaliser_versions_are_strings(provider: YFinanceProvider) -> None:
    assert all(isinstance(provider.normaliser_version(d), str) for d in ("prices", "fx"))


def test_normalise_accepts_stored_dict_payload(
    provider: YFinanceProvider, yf_payload: Loader
) -> None:
    payload = yf_payload("prices_BP.L")
    item = _item("BP.L", date(2026, 11, 1), date(2026, 11, 24))
    frame = provider.normalise(datasets.PRICES, _raw(item), payload.model_dump(mode="json"))
    assert set(frame["currency"]) == {"GBP"}
