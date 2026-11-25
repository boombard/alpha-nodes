"""DatasetFetch / DatasetFetchMany against a real DuckDB source store and fake providers."""

import contextlib
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import pytest
from lensgraph import RunSpec, arun
from lensgraph.node import NodeContext
from lensgraph.sources import DuckDBSourceStore, FakeClock, FetchOutcome, WorkItem
from lensgraph.sources.node import DatasetFetch, DatasetFetchMany
from lensgraph.store.memory import InMemoryBlobStore
from lensgraph.types import CandidateRef
from toy.sources_catalog import ASSAYS, STRAIN_INFO, FakeAssayProvider, FakeBulkAssayProvider
from toy.sources_nodes import LabUpper, build_registry

T0 = datetime(2026, 3, 10, 12, tzinfo=UTC)


class Assays(DatasetFetch):
    name: ClassVar[str] = "assays_node"
    dataset: ClassVar[str] = "assays"
    lookback_days: int | None = 4


class AssaysByAttr(Assays):
    name: ClassVar[str] = "assays_by_attr"
    entity_attr: str | None = "strain"


class Info(DatasetFetch):
    name: ClassVar[str] = "info_node"
    dataset: ClassVar[str] = "strain_info"


class Panel(DatasetFetchMany):
    name: ClassVar[str] = "panel_node"
    dataset: ClassVar[str] = "assays"
    entities: list[str] = ["A", "B", "C", "D", "E", "F", "G"]  # noqa: RUF012


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def make_store(clock: FakeClock, tmp_path: Path) -> Iterator[Any]:
    """Factory `make(provider, path=None, offline=False)`; closes every store at teardown."""
    stores: list[DuckDBSourceStore] = []

    def make(provider: Any, path: Path | None = None, offline: bool = False) -> DuckDBSourceStore:
        store = DuckDBSourceStore(
            path or tmp_path / "s.duckdb",
            InMemoryBlobStore(),
            {ASSAYS.name: ASSAYS, STRAIN_INFO.name: STRAIN_INFO},
            {ASSAYS.name: [provider], STRAIN_INFO.name: [provider]},
            clock=clock,
            offline=offline,
        )
        stores.append(store)
        return store

    yield make
    for s in stores:
        with contextlib.suppress(Exception):  # a test may have closed it already
            s.close()


def ctx_for(store: Any, cand: str | None = "S1", as_of: date | None = None, **attrs: Any) -> NodeContext:
    return NodeContext(
        run_id="r",
        candidate=CandidateRef(id=cand, attrs=attrs) if cand else None,
        as_of=as_of,
        services={"sources": store},
    )


async def test_dataset_fetch_window_ends_at_as_of_or_today(make_store: Any) -> None:
    provider = FakeAssayProvider()
    store = make_store(provider)
    live = await Assays().run(ctx_for(store))
    assert live["day"].dt.date.max() == date(2026, 3, 10)  # the store clock's today
    assert live["day"].dt.date.min() == date(2026, 3, 6)
    assert {"od600", "quality", "first_seen_at"} <= set(live.columns)  # canonical + meta
    provider.calls.clear()
    await Assays().run(ctx_for(store, as_of=date(2026, 3, 1)))  # as_of earlier: its own window is fetched
    (item,) = provider.calls[0]
    assert (item.interval.start, item.interval.end) == (date(2026, 2, 25), date(2026, 3, 1))  # type: ignore[union-attr]


async def test_dataset_fetch_entity_attr(make_store: Any) -> None:
    provider = FakeAssayProvider()
    store = make_store(provider)
    await AssaysByAttr().run(ctx_for(store, "cand-1", strain="S9"))
    assert [i.entity for call in provider.calls for i in call] == ["S9"]


async def test_empty_slice_is_empty_frame_not_failure(make_store: Any) -> None:
    provider = FakeAssayProvider()
    provider.unknown = {"S1"}
    frame = await Assays().run(ctx_for(make_store(provider)))
    assert isinstance(frame, pd.DataFrame)
    assert frame.empty


async def test_source_unavailable_fails_node_and_skips_dependents(make_store: Any, tmp_path: Path) -> None:
    path = tmp_path / "offline.duckdb"
    make_store(FakeAssayProvider(), path=path).close()  # create the file, nothing fetched
    provider = FakeAssayProvider()
    store = make_store(provider, path=path, offline=True)
    registry = build_registry()
    result = await arun(
        RunSpec(targets=["assay_mean"], candidates=[CandidateRef(id="S1")]),
        registry,
        store_root=tmp_path / "root",
        services={"sources": store},
    )
    status = {k.name: r.status for k, r in result.results.items()}
    assert status["strain_assays"] == "failed"
    assert status["assay_mean"] == "skipped"
    assert provider.calls == []


async def test_fetch_many_one_ensure_call_batches(make_store: Any) -> None:
    provider = FakeBulkAssayProvider()  # max_batch=5
    store = make_store(provider)
    frame = await Panel(lookback_days=2).run(ctx_for(store, None))
    assert len(provider.calls) == 2  # 7 entities -> batches of 5 and 2
    assert sorted(frame["entity"].unique()) == list("ABCDEFG")
    assert list(frame["entity"]) == sorted(frame["entity"])


async def test_downstream_reruns_only_when_slice_changes(make_store: Any, clock: FakeClock, tmp_path: Path) -> None:
    class Changing(FakeAssayProvider):
        lab = "lab-a"

        def fetch(self, dataset: Any, items: list[WorkItem]) -> list[FetchOutcome]:
            outcomes = super().fetch(dataset, items)
            if dataset.name != "strain_info":
                return outcomes
            payload = pd.DataFrame({"label": ["x"], "lab": [self.lab]})
            return [o.model_copy(update={"payload": payload}) for o in outcomes]

    provider = Changing()
    store = make_store(provider)
    LabUpper.RUNS.clear()

    async def go() -> dict[str, bool]:
        res = await arun(
            RunSpec(targets=["lab_upper"], candidates=[CandidateRef(id="S1")]),
            build_registry(),
            store_root=tmp_path / "root",
            services={"sources": store},
        )
        return {k.name: r.cache_hit for k, r in res.results.items()}

    await go()
    assert LabUpper.RUNS == ["S1"]
    await go()  # no new data
    assert LabUpper.RUNS == ["S1"]
    clock.advance(91 * 86400)  # snapshot due again, same values
    await go()
    assert LabUpper.RUNS == ["S1"]
    provider.lab = "lab-b"
    clock.advance(91 * 86400)  # due again, and the provider restated
    await go()
    assert LabUpper.RUNS == ["S1", "S1"]


async def test_fetch_many_all_empty_keeps_columns(make_store: Any, tmp_path: Path) -> None:
    full = await Panel(lookback_days=2).run(ctx_for(make_store(FakeAssayProvider()), None))
    provider = FakeAssayProvider()
    provider.unknown = set("ABCDEFG")
    store = make_store(provider, path=tmp_path / "empty.duckdb")
    empty = await Panel(lookback_days=2).run(ctx_for(store, None))
    assert empty.empty
    assert list(empty.columns) == list(full.columns)
    assert empty.dtypes.astype(str).to_dict() == full.dtypes.astype(str).to_dict()


def test_fetch_many_rejects_empty_entities() -> None:
    from pydantic import ValidationError

    class Bare(DatasetFetchMany):
        name: ClassVar[str] = "bare"
        dataset: ClassVar[str] = "assays"

    with pytest.raises(ValidationError, match="entities"):
        Bare(entities=[])
