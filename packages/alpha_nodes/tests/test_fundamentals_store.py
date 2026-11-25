"""The DuckDB source store with the fundamentals and news datasets: nullable keys, restatements, as-of."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alpha_nodes.datasets import FUNDAMENTALS, NEWS
from lensgraph.sources import (
    Dataset,
    DuckDBSourceStore,
    FakeClock,
    FetchOutcome,
    ProviderCapabilities,
    RateLimitPolicy,
    RawResponse,
    WorkItem,
)
from lensgraph.store.memory import InMemoryBlobStore

T0 = datetime(2026, 3, 10, 12, tzinfo=UTC)
ENTITY = "AAA"


class FakeStatementsProvider:
    """Serves whatever frame the test put in `frames[dataset]`, normalised as-is with quality ok."""

    name = "fake"
    library_version = "test-1"
    capabilities = ProviderCapabilities(
        datasets=frozenset({FUNDAMENTALS.name, NEWS.name}),
        rate_limit=RateLimitPolicy(concurrency=1, per_second=100, burst=10),
    )

    def __init__(self) -> None:
        self.frames: dict[str, pd.DataFrame] = {}

    def normaliser_version(self, dataset: str) -> str:
        return "1"

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        return [FetchOutcome(item=i, kind="ok", payload=self.frames[dataset.name]) for i in items]

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        frame = pd.DataFrame(payload).copy()
        frame["repairs"] = [[] for _ in range(len(frame))]
        frame["quality"] = "ok"
        frame["quality_reasons"] = [[] for _ in range(len(frame))]
        if dataset.name == NEWS.name:
            frame["known_at"] = frame["published_at"]
        elif bool(frame["filed_at"].notna().all()):
            frame["known_at"] = frame["filed_at"].dt.tz_localize("UTC")
        else:  # yfinance-like: no filing dates, so known_at is first seen
            frame["known_at"] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
        return frame


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def provider() -> FakeStatementsProvider:
    return FakeStatementsProvider()


@pytest.fixture
def store(tmp_path: Path, clock: FakeClock, provider: FakeStatementsProvider) -> Iterator[DuckDBSourceStore]:
    s = DuckDBSourceStore(
        tmp_path / "sources.duckdb",
        InMemoryBlobStore(),
        {FUNDAMENTALS.name: FUNDAMENTALS, NEWS.name: NEWS},
        {FUNDAMENTALS.name: [provider], NEWS.name: [provider]},
        clock=clock,
    )
    yield s
    s.close()


async def test_fundamentals_roundtrip_with_null_filed_at(
    store: DuckDBSourceStore, provider: FakeStatementsProvider, fundamentals_frame: pd.DataFrame
) -> None:
    provider.frames["fundamentals"] = fundamentals_frame.iloc[:1]  # the null-filed_at period only
    got = (await store.get("fundamentals", ENTITY, None)).frame
    assert len(got) == 1
    assert pd.isna(got["filed_at"].iloc[0])
    assert got["period_end"].iloc[0] == pd.Timestamp("2023-12-31")
    assert got["revenue"].iloc[0] == 1000.0 and pd.isna(got["interest_expense"].iloc[0])
    assert got["known_at"].iloc[0] == pd.Timestamp(T0)  # first seen

    provider.frames["fundamentals"] = fundamentals_frame  # a null and a dated period together
    await store.ensure("fundamentals", [ENTITY], None)  # fresh: no refetch
    assert len(store.query("fundamentals", ENTITY, None).frame) == 1


async def test_null_and_dated_periods_are_served_together(
    store: DuckDBSourceStore, provider: FakeStatementsProvider, fundamentals_frame: pd.DataFrame
) -> None:
    provider.frames["fundamentals"] = fundamentals_frame
    got = (await store.get("fundamentals", ENTITY, None)).frame
    assert got["period_end"].dt.year.tolist() == [2023, 2024]
    assert got["filed_at"].isna().tolist() == [True, False]


async def test_two_filings_of_one_period_are_distinct_facts(
    store: DuckDBSourceStore, provider: FakeStatementsProvider, fundamentals_frame: pd.DataFrame
) -> None:
    original = fundamentals_frame.iloc[[1]].copy()  # 10-K filed 2025-03-01
    amended = original.assign(filed_at=pd.Timestamp("2025-09-15"), net_income=95.0)  # 10-K/A, restated
    provider.frames["fundamentals"] = pd.concat([original, amended], ignore_index=True)
    got = (await store.get("fundamentals", ENTITY, None)).frame
    assert len(got) == 2
    assert len(set(got["period_end"])) == 1
    assert got.sort_values("filed_at")["net_income"].tolist() == [90.0, 95.0]
    assert got.sort_values("filed_at")["known_at"].dt.date.tolist() == [date(2025, 3, 1), date(2025, 9, 15)]


async def test_as_of_sees_only_filings_known_then(
    store: DuckDBSourceStore, provider: FakeStatementsProvider, fundamentals_frame: pd.DataFrame
) -> None:
    original = fundamentals_frame.iloc[[1]].copy()
    amended = original.assign(filed_at=pd.Timestamp("2025-09-15"), net_income=95.0)
    provider.frames["fundamentals"] = pd.concat([original, amended], ignore_index=True)
    await store.get("fundamentals", ENTITY, None)

    def seen(as_of: date) -> list[float]:
        return store.query("fundamentals", ENTITY, None, as_of=as_of).frame.sort_values("filed_at")["net_income"].tolist()

    assert seen(date(2025, 2, 28)) == []
    assert seen(date(2025, 3, 1)) == [90.0]
    assert seen(date(2025, 9, 14)) == [90.0]
    assert seen(date(2025, 9, 15)) == [90.0, 95.0]


async def test_news_items_accumulate_across_snapshots(
    store: DuckDBSourceStore, provider: FakeStatementsProvider, clock: FakeClock, news_frame: pd.DataFrame
) -> None:
    provider.frames["news"] = news_frame.iloc[:1]
    assert (await store.get("news", ENTITY, None)).frame["id"].tolist() == ["a1"]

    provider.frames["news"] = news_frame.iloc[1:].assign(id=["b1"])  # a different item set
    clock.advance(timedelta(days=1, hours=1).total_seconds())  # past the 1-day TTL
    got = (await store.get("news", ENTITY, None)).frame
    assert sorted(got["id"]) == ["a1", "b1"]
    assert got["published_at"].dt.tz is not None
