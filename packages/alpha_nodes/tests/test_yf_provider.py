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
from alpha_nodes.providers.yfinance.fundamentals import YFStatementsPayload
from alpha_nodes.providers.yfinance.history import YFHistoryPayload
from alpha_nodes.providers.yfinance.profile import YFProfilePayload
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
    DuckDBSourceStore,
    FakeClock,
    RawResponse,
    WorkItem,
)
from lensgraph.store.memory import InMemoryBlobStore
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError, YFTzMissingError

from .conftest import yf_frame
from .yf_replay import YFReplay

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
    assert caps.datasets == {"prices", "fx", "profile", "fundamentals", "news"}
    assert caps.max_batch == 1
    assert caps.rate_limit == YF_POLICY
    assert caps.pit_reliable == {
        "prices": True,
        "fx": True,
        "profile": False,
        "fundamentals": False,
        "news": False,
    }
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


WEEKDAYS = (date(2026, 11, 20), date(2026, 11, 24))  # Fri..Tue: sessions inside
WEEKEND = (date(2026, 11, 21), date(2026, 11, 22))  # Sat..Sun: no sessions


@pytest.mark.parametrize(
    ("error", "tz", "span", "kind", "settled"),
    [
        (YFRateLimitError(), None, WEEKDAYS, "rate_limited", False),
        (YFTzMissingError("X.L"), None, WEEKDAYS, "empty", False),
        (YFPricesMissingError("X.L", ""), None, WEEKDAYS, "empty", False),
        # known tz: only a range without sessions is an empty interval; otherwise retry
        (YFPricesMissingError("X.L", ""), "Europe/London", WEEKEND, "ok", True),
        (YFPricesMissingError("X.L", ""), "Europe/London", WEEKDAYS, "error", False),
        (_http_error(404), None, WEEKDAYS, "empty", False),
        (_http_error(404), "Europe/London", WEEKDAYS, "error", False),
        (_http_error(500), None, WEEKDAYS, "error", False),
        (_http_error(401), None, WEEKDAYS, "rate_limited", False),
        (_http_error(403), None, WEEKDAYS, "rate_limited", False),
        (ValueError("Invalid Crumb"), None, WEEKDAYS, "rate_limited", False),
        (RuntimeError("401 Unauthorized"), None, WEEKDAYS, "rate_limited", False),
        (CurlConnectionError("down"), None, WEEKDAYS, "unreachable", False),
        (CurlTimeout("slow"), None, WEEKDAYS, "unreachable", False),
        (TimeoutError("slow"), None, WEEKDAYS, "unreachable", False),
        (ValueError("boom"), None, WEEKDAYS, "error", False),
    ],
)
def test_exceptions_classified(
    provider: YFinanceProvider,
    stub: YFStub,
    error: Exception,
    tz: str | None,
    span: tuple[date, date],
    kind: str,
    settled: bool,
) -> None:
    stub.answers["X.L"] = error
    if tz:
        stub.known_tz["X.L"] = tz
    outcome = _fetch(provider, _item("X.L", *span))
    assert outcome.kind == kind
    assert (outcome.settled_through is not None) is settled
    if kind == "error":
        assert str(error) in outcome.message
    if kind == "ok":
        assert outcome.payload.data == []  # an empty interval, not an empty entity
        frame = provider.normalise(datasets.PRICES, _raw(outcome.item), outcome.payload)
        assert frame.empty


def test_unknown_suffix_is_empty_not_raised(provider: YFinanceProvider) -> None:
    outcome = _fetch(provider, _item("FOO.ZZ", *WEEKDAYS))
    assert outcome.kind == "empty"
    assert ".ZZ" in outcome.message


def _drop_last_bars(payload: YFHistoryPayload, n: int) -> YFHistoryPayload:
    """Constructed variant: the last `n` bars removed (Yahoo not yet serving them)."""
    payload.index, payload.data = payload.index[:-n], payload.data[:-n]
    return payload


def test_missing_tail_caps_settled_through(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    """Constructed variant: ASML without its last two bars (11-23, 11-24); last is Fri 11-20."""
    stub.answers["ASML.AS"] = _drop_last_bars(yf_payload("prices_ASML.AS"), 2)
    outcome = _fetch(provider, _item("ASML.AS", date(2026, 11, 18), date(2026, 11, 24)))
    assert outcome.kind == "ok"
    assert outcome.settled_through == date(2026, 11, 20)


def test_old_last_bar_does_not_cap_settled_through(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    """Constructed variant: a suspended name whose last bar is weeks old; no cap."""
    stub.answers["ASML.AS"] = _drop_last_bars(yf_payload("prices_ASML.AS"), 15)
    outcome = _fetch(provider, _item("ASML.AS", date(2026, 11, 18), date(2026, 11, 24)))
    assert outcome.kind == "ok"
    assert outcome.settled_through == date(2026, 11, 24)


def test_fx_missing_tail_caps_settled_through(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    """Constructed variant: GBPUSD without its last bar; the cap counts calendar days."""
    payload = yf_payload("fx_GBPUSD=X")
    last = date.fromisoformat(payload.index[-1][:10])
    assert last == date(2026, 11, 24)
    stub.answers["GBPUSD=X"] = _drop_last_bars(payload, 1)
    prev = date.fromisoformat(payload.index[-1][:10])
    outcome = _fetch(provider, _item("GBP", date(2026, 11, 1), date(2026, 11, 24), "fx"))
    assert outcome.settled_through == prev


def test_truncated_history_is_error(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    """Constructed variant: ASML history missing its first 20 bars after the requested start."""
    payload = yf_payload("prices_ASML.AS")
    payload.index, payload.data = payload.index[20:], payload.data[20:]
    stub.answers["ASML.AS"] = payload
    outcome = _fetch(provider, _item("ASML.AS", date(2024, 11, 25), date(2026, 11, 24)))
    assert outcome.kind == "error"
    assert "history truncated" in outcome.message


def test_history_starting_at_first_trade_date_not_truncated(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    """A request reaching before the listing starts at firstTradeDate: not a truncation."""
    payload = yf_payload("prices_ASML.AS")
    first = payload.index[0][:10]
    payload.metadata["firstTradeDate"] = f"{first} 09:00:00+01:00"
    stub.answers["ASML.AS"] = payload
    outcome = _fetch(provider, _item("ASML.AS", date(2020, 1, 2), date(2026, 11, 24)))
    assert outcome.kind == "ok"


@pytest.mark.parametrize("first_trade", [None, "not a date"])
def test_truncation_check_skipped_without_first_trade_date(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader, first_trade: str | None
) -> None:
    """Constructed variant: first 20 bars missing, but no usable firstTradeDate: fail open."""
    payload = yf_payload("prices_ASML.AS")
    payload.index, payload.data = payload.index[20:], payload.data[20:]
    payload.metadata.pop("firstTradeDate", None)
    if first_trade:
        payload.metadata["firstTradeDate"] = first_trade
    stub.answers["ASML.AS"] = payload
    outcome = _fetch(provider, _item("ASML.AS", date(2024, 11, 25), date(2026, 11, 24)))
    assert outcome.kind == "ok"


def test_fx_weekend_missing_is_ok_empty(provider: YFinanceProvider, stub: YFStub) -> None:
    """Fx does not trade at weekends: a weekend-only range with no bars is an empty interval."""
    stub.answers["GBPUSD=X"] = YFPricesMissingError("GBPUSD=X", "")
    stub.known_tz["GBPUSD=X"] = "UTC"
    outcome = _fetch(provider, _item("GBP", date(2026, 11, 21), date(2026, 11, 22), "fx"))
    assert outcome.kind == "ok"
    assert outcome.payload.data == []


def test_fx_weekday_missing_is_error(provider: YFinanceProvider, stub: YFStub) -> None:
    stub.answers["GBPUSD=X"] = YFPricesMissingError("GBPUSD=X", "")
    stub.known_tz["GBPUSD=X"] = "UTC"
    outcome = _fetch(provider, _item("GBP", date(2026, 11, 20), date(2026, 11, 22), "fx"))
    assert outcome.kind == "error"


def test_fx_settled_on_weekend_with_friday_bar_not_capped(
    provider: YFinanceProvider, stub: YFStub, clock: FakeClock, yf_payload: Loader
) -> None:
    """Constructed variant: GBPUSD ending Fri 11-20 while settled is Sun 11-22."""
    payload = yf_payload("fx_GBPUSD=X")
    keep = [i for i, ts in enumerate(payload.index) if ts[:10] <= "2026-11-20"]
    payload.index = [payload.index[i] for i in keep]
    payload.data = [payload.data[i] for i in keep]
    assert payload.index[-1][:10] == "2026-11-20"
    stub.answers["GBPUSD=X"] = payload
    clock._now = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)  # Monday: settled = Sunday 11-22
    outcome = _fetch(provider, _item("GBP", date(2026, 11, 1), date(2026, 11, 22), "fx"))
    assert outcome.settled_through == date(2026, 11, 22)


def test_yf_policy_sets_breakers() -> None:
    assert YF_POLICY.max_consecutive_errors == 5
    assert YF_POLICY.max_consecutive_empty == 20


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


def _listed_from_first_bar(payload: YFHistoryPayload) -> YFHistoryPayload:
    """Constructed variant: the short split fixture as if the listing began at its first bar,
    so the truncated-history check does not see it as a cut-off response."""
    payload.metadata["firstTradeDate"] = f"{payload.index[0][:10]} 09:30:00-04:00"
    return payload


def test_split_in_top_up_sets_restated_before(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    stub.answers["AAPL"] = _listed_from_first_bar(yf_payload("split_AAPL"))
    outcome = _fetch(provider, _item("AAPL", date(2020, 8, 28), date(2020, 9, 3)))
    assert outcome.restated_before == date(2020, 8, 31)


def test_split_far_after_requested_start_not_a_restatement(
    provider: YFinanceProvider, stub: YFStub, yf_payload: Loader
) -> None:
    """A backfill starting over two years before the split already holds nothing to restate."""
    stub.answers["AAPL"] = _listed_from_first_bar(yf_payload("split_AAPL"))
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


def test_capabilities_include_fundamentals_and_news_not_pit_reliable(
    provider: YFinanceProvider,
) -> None:
    caps = provider.capabilities
    assert {"fundamentals", "news"} <= caps.datasets
    assert caps.pit_reliable["fundamentals"] is False
    assert caps.pit_reliable["news"] is False
    assert provider.normaliser_version("fundamentals") == "1"
    assert provider.normaliser_version("news") == "1"


def _entity_item(dataset: str, entity: str) -> WorkItem:
    return WorkItem(dataset=dataset, entity=entity, interval=None)


def test_fundamentals_fetch_and_normalise_round_trip(replay: YFReplay, tmp_path: Path) -> None:
    provider = YFinanceProvider(tmp_path, FakeClock(NOW))
    outcome = _fetch(provider, _entity_item("fundamentals", "BP.L"))
    assert outcome.kind == "ok"
    assert outcome.settled_through is None
    frame = provider.normalise(
        datasets.FUNDAMENTALS, _raw(outcome.item), outcome.payload.model_dump(mode="json")
    )
    assert set(frame["currency"]) == {"USD"}
    assert bool((frame["capex"].dropna() >= 0).all())
    assert {c.kind for c in replay.calls} == {"info", "statements"}


def test_fundamentals_all_empty_statements_is_error(replay: YFReplay, tmp_path: Path) -> None:
    """Known symbol (`.info` has a currency) but Yahoo returned no statements: retry, never cache."""
    empty = {"columns": [], "index": [], "data": []}
    replay.statements["BP.L"] = YFStatementsPayload(
        symbol="BP.L",
        income=empty,
        balance=empty,
        cashflow=empty,
        financial_currency="USD",
        info_net_income=None,
    )
    outcome = _fetch(
        YFinanceProvider(tmp_path, FakeClock(NOW)), _entity_item("fundamentals", "BP.L")
    )
    assert outcome.kind == "error"
    assert "empty" in outcome.message


def test_fundamentals_one_empty_statement_is_still_ok(replay: YFReplay, tmp_path: Path) -> None:
    """BP.L's yearly balance sheet can be short, but only all three empty is the transient quirk."""
    empty = {"columns": [], "index": [], "data": []}
    payload = replay._statements("BP.L")
    assert payload is not None
    replay.statements["BP.L"] = payload.model_copy(update={"balance": empty})
    outcome = _fetch(
        YFinanceProvider(tmp_path, FakeClock(NOW)), _entity_item("fundamentals", "BP.L")
    )
    assert outcome.kind == "ok"


def test_fundamentals_unknown_symbol_is_empty(replay: YFReplay, tmp_path: Path) -> None:
    provider = YFinanceProvider(tmp_path, FakeClock(NOW))
    assert _fetch(provider, _entity_item("fundamentals", "NOSUCH.L")).kind == "empty"  # HTTP 404
    replay.profiles["GONE.L"] = YFProfilePayload(
        symbol="GONE.L", info={"trailingPegRatio": None}, isin=None
    )
    stub = _fetch(provider, _entity_item("fundamentals", "GONE.L"))  # Yahoo's currency-less stub
    assert stub.kind == "empty"


def test_news_fetch_ok_and_empty_news_is_ok(replay: YFReplay, tmp_path: Path) -> None:
    provider = YFinanceProvider(tmp_path, FakeClock(NOW))
    outcome = _fetch(provider, _entity_item("news", "AAPL"))
    assert outcome.kind == "ok"
    assert len(provider.normalise(datasets.NEWS, _raw(outcome.item), outcome.payload)) > 0
    quiet = _fetch(provider, _entity_item("news", "QUIET.L"))  # no fixture: get_news returns []
    assert quiet.kind == "ok"
    assert provider.normalise(datasets.NEWS, _raw(quiet.item), quiet.payload).empty


def test_news_errors_are_classified(
    provider: YFinanceProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Ticker:
        def get_news(self, **_: Any) -> list[dict[str, Any]]:
            raise YFRateLimitError()

    monkeypatch.setattr(provider_mod.yf, "Ticker", lambda _symbol: _Ticker())
    assert _fetch(provider, _entity_item("news", "AAPL")).kind == "rate_limited"


async def test_rejected_null_currency_rows_round_trip_through_the_store(
    replay: YFReplay, tmp_path: Path
) -> None:
    """A payload with no `financialCurrency` is stored as rejected rows with a null currency."""
    payload = replay._statements("BP.L")
    assert payload is not None
    replay.statements["BP.L"] = payload.model_copy(update={"financial_currency": None})
    provider = YFinanceProvider(tmp_path, FakeClock(NOW))
    store = DuckDBSourceStore(
        tmp_path / "sources.duckdb",
        InMemoryBlobStore(),
        {"fundamentals": datasets.FUNDAMENTALS},
        {"fundamentals": [provider]},
        clock=FakeClock(NOW),
    )
    try:
        await store.get("fundamentals", "BP.L", None)
        assert store.query("fundamentals", "BP.L", None).frame.empty  # rejected rows are hidden
        got = store.query("fundamentals", "BP.L", None, include_rejected=True).frame
    finally:
        store.close()
    assert len(got) == 5  # four annual periods plus Yahoo's sparse fifth column, also rejected
    assert bool(got["currency"].isna().all())
    assert set(got["quality"]) == {"rejected"}
    assert all("no_currency" in r for r in got["quality_reasons"])
