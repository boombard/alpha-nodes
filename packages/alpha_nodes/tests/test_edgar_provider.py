"""`EdgarProvider` against the recorded SEC fixtures (no network), and its place in a store chain."""

import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alpha_nodes.catalog import CATALOG
from alpha_nodes.datasets import FUNDAMENTALS
from alpha_nodes.providers.edgar.provider import EDGAR_POLICY, EdgarProvider
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from lensgraph.sources import (
    Dataset,
    DuckDBSourceStore,
    FakeClock,
    FetchOutcome,
    ProviderCapabilities,
    ProviderContext,
    RateLimitPolicy,
    RawResponse,
    WorkItem,
)
from lensgraph.store.memory import InMemoryBlobStore

from .edgar_replay import EdgarReplay

UA = "test-agent contact@example.invalid"


@pytest.fixture
def provider(tmp_path: Path, clock: FakeClock, edgar_replay: EdgarReplay) -> EdgarProvider:
    return EdgarProvider(tmp_path, clock, user_agent=UA)


def _fetch(provider: EdgarProvider, symbol: str) -> FetchOutcome:
    (outcome,) = provider.fetch(FUNDAMENTALS, [WorkItem(dataset="fundamentals", entity=symbol, interval=None)])
    return outcome


def test_ok_outcome_carries_payload_and_sends_user_agent(provider: EdgarProvider, edgar_replay: EdgarReplay) -> None:
    outcome = _fetch(provider, "AAPL")
    assert outcome.kind == "ok" and outcome.payload.cik == 320193
    assert {r.user_agent for r in edgar_replay.requests} == {UA}
    assert len(edgar_replay.requests) == 2  # ticker map, company facts


def test_suffixed_symbol_is_empty_without_request(provider: EdgarProvider, edgar_replay: EdgarReplay) -> None:
    assert _fetch(provider, "BP.L").kind == "empty"
    assert edgar_replay.requests == []


def test_unknown_ticker_is_empty(provider: EdgarProvider, edgar_replay: EdgarReplay) -> None:
    assert _fetch(provider, "NOSUCH").kind == "empty"
    assert [r.url for r in edgar_replay.requests] == ["https://www.sec.gov/files/company_tickers.json"]


def test_ticker_map_cached_for_7_days(
    provider: EdgarProvider, edgar_replay: EdgarReplay, clock: FakeClock, tmp_path: Path
) -> None:
    _fetch(provider, "AAPL")
    assert (tmp_path / "company_tickers.json").exists()
    _fetch(provider, "KO")
    assert sum(r.url.endswith("company_tickers.json") for r in edgar_replay.requests) == 1
    clock.advance(timedelta(days=7, seconds=1).total_seconds())
    _fetch(provider, "KO")
    assert sum(r.url.endswith("company_tickers.json") for r in edgar_replay.requests) == 2


def test_ticker_lookup_is_case_insensitive(provider: EdgarProvider) -> None:
    assert _fetch(provider, "aapl").kind == "ok"


def test_company_without_usgaap_facts_is_empty(provider: EdgarProvider, edgar_replay: EdgarReplay) -> None:
    edgar_replay.tickers_doc["9"] = {"cik_str": 1, "ticker": "FOO", "title": "Foo"}
    from alpha_nodes.providers.edgar import provider as mod

    original = edgar_replay._body
    edgar_replay._body = lambda url: (  # type: ignore[method-assign]
        json.dumps({"cik": 1, "facts": {"ifrs-full": {}}}).encode()
        if url == mod.companyfacts_url(1)
        else original(url)
    )
    assert _fetch(provider, "FOO").kind == "empty"


@pytest.mark.parametrize("status", [429, 403])
def test_http_429_is_rate_limited(provider: EdgarProvider, edgar_replay: EdgarReplay, status: int) -> None:
    edgar_replay.fail_with = status
    assert _fetch(provider, "AAPL").kind == "rate_limited"


def test_connection_error_is_unreachable(provider: EdgarProvider, edgar_replay: EdgarReplay) -> None:
    edgar_replay.fail_with = CurlConnectionError("no route")
    assert _fetch(provider, "AAPL").kind == "unreachable"


def test_other_http_error_is_error(provider: EdgarProvider, edgar_replay: EdgarReplay) -> None:
    edgar_replay.fail_with = 500
    assert _fetch(provider, "AAPL").kind == "error"


def test_capabilities_and_breakers(provider: EdgarProvider) -> None:
    caps = provider.capabilities
    assert caps.datasets == {"fundamentals"} and caps.max_batch == 1
    assert caps.rate_limit is EDGAR_POLICY and EDGAR_POLICY.max_consecutive_empty is None
    assert caps.pit_reliable == {"fundamentals": True}
    assert provider.name == "edgar" and provider.normaliser_version("fundamentals")


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_user_agent_rejected(tmp_path: Path, blank: str) -> None:
    with pytest.raises(ValueError, match="user_agent"):
        EdgarProvider(tmp_path, user_agent=blank)


def test_catalog_factory_requires_user_agent(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = ProviderContext(cache_dir=tmp_path / "edgar", clock=clock)
    monkeypatch.delenv("ALPHA_NODES_SEC_USER_AGENT", raising=False)
    with pytest.raises(ValueError, match="ALPHA_NODES_SEC_USER_AGENT"):
        CATALOG.providers["edgar"](ctx)
    monkeypatch.setenv("ALPHA_NODES_SEC_USER_AGENT", UA)
    assert CATALOG.providers["edgar"](ctx).name == "edgar"


class FakeFundamentalsProvider:
    """Stands in for yfinance: serves the shared one-period GBP frame (no filing date) for any symbol."""

    name = "fake"
    library_version = "test-1"
    capabilities = ProviderCapabilities(
        datasets=frozenset({"fundamentals"}), rate_limit=RateLimitPolicy(concurrency=1, per_second=100, burst=10)
    )

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def normaliser_version(self, dataset: str) -> str:
        return "1"

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        return [FetchOutcome(item=i, kind="ok", payload={"x": 1}) for i in items]

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        frame = self.frame.iloc[:1].copy()
        frame["repairs"] = [[]]
        frame["quality"] = "ok"
        frame["quality_reasons"] = [[]]
        frame["known_at"] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
        return frame


@pytest.fixture
def store(
    tmp_path: Path, provider: EdgarProvider, clock: FakeClock, fundamentals_frame: pd.DataFrame
) -> Iterator[DuckDBSourceStore]:
    s = DuckDBSourceStore(
        tmp_path / "sources.duckdb", InMemoryBlobStore(), {"fundamentals": FUNDAMENTALS},
        {"fundamentals": [provider, FakeFundamentalsProvider(fundamentals_frame)]}, clock=clock,
    )
    yield s
    s.close()


async def test_store_fallback_edgar_then_fake_yfinance(store: DuckDBSourceStore) -> None:
    aapl = await store.get("fundamentals", "AAPL", None)
    assert aapl.provider == "edgar" and aapl.pit_reliable and len(aapl.frame) >= 8
    assert bool(aapl.frame["known_at"].notna().all())
    bp = await store.get("fundamentals", "BP.L", None)
    assert bp.provider == "fake" and not bp.pit_reliable and bp.frame["currency"].iloc[0] == "GBP"
