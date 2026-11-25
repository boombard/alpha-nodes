"""DuckDB point-in-time source store: persistence, versions, fallback, resume, offline, renormalise."""

from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from lensgraph.sources import (
    FACT_META_COLUMNS,
    Dataset,
    DateInterval,
    DuckDBSourceStore,
    FakeClock,
    FetchOutcome,
    Provider,
    RateLimitPolicy,
    RawResponse,
    SourceSlice,
    SourceUnavailable,
    WorkItem,
)
from lensgraph.store.memory import InMemoryBlobStore
from lensgraph.types import GlobalFailure
from toy import sources_catalog
from toy.sources_catalog import ASSAYS, STRAIN_INFO, FakeAssayProvider, FakeBulkAssayProvider

T0 = datetime(2026, 3, 10, 12, tzinfo=UTC)
MakeStore = Callable[..., DuckDBSourceStore]


def march(a: int, b: int | None = None) -> DateInterval:
    """The closed interval of March 2026 days `a`..`b` (a single day when `b` is omitted)."""
    return DateInterval(start=date(2026, 3, a), end=date(2026, 3, b or a))


def day(d: int) -> date:
    return date(2026, 3, d)


class RestatingProvider(FakeAssayProvider):
    """Reports `restated_before` on every ok date-axis outcome while it is set."""

    def __init__(self, name: str = "fake") -> None:
        super().__init__(name)
        self.restated_before: date | None = None

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        outcomes = super().fetch(dataset, items)
        return [
            o.model_copy(update={"restated_before": self.restated_before})
            if o.kind == "ok" and o.item.interval is not None
            else o
            for o in outcomes
        ]


class FlaggingProvider(FakeAssayProvider):
    """Marks `rejected_days` as rejected and, when `publish_lag` is set, reports `known_at`."""

    def __init__(self, name: str = "fake") -> None:
        super().__init__(name)
        self.rejected_days: set[date] = set()
        self.publish_lag: timedelta | None = None

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        frame = super().normalise(dataset, raw, payload)
        if dataset.name == ASSAYS.name:
            bad = frame["day"].dt.date.isin(self.rejected_days)
            frame.loc[bad, "quality"] = "rejected"
            frame.loc[bad, "quality_reasons"] = pd.Series([["bad_row"]] * int(bad.sum()), index=frame.index[bad])
            if self.publish_lag is not None:
                frame["known_at"] = (frame["day"] + self.publish_lag).dt.tz_localize("UTC")
        return frame


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def fake() -> FakeAssayProvider:
    return FakeAssayProvider()


@pytest.fixture
def bulk() -> FakeBulkAssayProvider:
    return FakeBulkAssayProvider()


@pytest.fixture
def blobs() -> InMemoryBlobStore:
    return InMemoryBlobStore()


@pytest.fixture
def make_store(
    clock: FakeClock, blobs: InMemoryBlobStore, fake: FakeAssayProvider
) -> Iterator[MakeStore]:
    """Factory for stores over the toy datasets; every store it makes is closed at teardown."""
    stores: list[DuckDBSourceStore] = []

    def make(
        *,
        assays: Sequence[Provider] | None = None,
        info: Sequence[Provider] | None = None,
        path: Path | str = ":memory:",
        **kwargs: Any,
    ) -> DuckDBSourceStore:
        store = DuckDBSourceStore(
            path,
            blobs,
            {ASSAYS.name: ASSAYS, STRAIN_INFO.name: STRAIN_INFO},
            {ASSAYS.name: assays or [fake], STRAIN_INFO.name: info or assays or [fake]},
            clock=kwargs.pop("clock", clock),
            **kwargs,
        )
        stores.append(store)
        return store

    yield make
    for store in stores:
        store.close()


async def get(
    store: DuckDBSourceStore, entity: str = "S1", a: int = 1, b: int = 3, **kwargs: Any
) -> SourceSlice:
    return await store.get("assays", entity, march(a, b), **kwargs)


def days_of(slice_: SourceSlice) -> list[int]:
    return [d.day for d in slice_.frame["day"]]


def version_count(store: DuckDBSourceStore, dataset: str = "assays") -> int:
    return store._con.execute(f'SELECT count(*) FROM "facts_{dataset}"').fetchone()[0]  # type: ignore[index]


async def test_second_get_makes_no_provider_calls(make_store: MakeStore, fake: FakeAssayProvider) -> None:
    store = make_store()
    first = await get(store)
    second = await get(store)
    assert len(fake.calls) == 1
    assert days_of(first) == days_of(second) == [1, 2, 3]
    assert second.provider == "fake" and second.pit_reliable and not second.empty
    assert set(FACT_META_COLUMNS) <= set(second.frame.columns) and "od600" in second.frame.columns


async def test_mid_range_hole_fetches_only_the_hole(make_store: MakeStore, fake: FakeAssayProvider) -> None:
    store = make_store()
    await get(store, a=1, b=3)
    await get(store, a=7, b=9)
    slice_ = await get(store, a=1, b=9)
    assert [c[0].interval for c in fake.calls] == [march(1, 3), march(7, 9), march(4, 6)]
    assert days_of(slice_) == list(range(1, 10))


async def test_rows_after_settled_not_stored_and_tail_logged(
    make_store: MakeStore, fake: FakeAssayProvider
) -> None:
    fake.settled_through = day(3)
    store = make_store()
    slice_ = await get(store, a=1, b=5)
    assert days_of(slice_) == [1, 2, 3]
    assert version_count(store) == 3
    assert store.coverage("assays", "S1", "fake").intervals == (march(1, 3),)
    unsettled = [a for a in store.attempts("assays", "S1") if a.kind == "unsettled"]
    assert [a.interval for a in unsettled] == [march(4, 5)]


async def test_unchanged_refetch_adds_no_version(
    make_store: MakeStore, fake: FakeAssayProvider, clock: FakeClock
) -> None:
    store = make_store()
    await store.get("strain_info", "S1")
    clock.advance(91 * 86400)
    await store.get("strain_info", "S1")
    assert len(fake.calls) == 2  # refetched after the ttl...
    assert version_count(store, "strain_info") == 1  # ...but nothing changed


async def test_relabel_only_adds_version(
    make_store: MakeStore, fake: FakeAssayProvider, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.spike_days = {day(2)}
    store = make_store()
    before = await get(store)
    assert before.frame.loc[before.frame["day"].dt.day == 2, "quality"].item() == "suspect"
    clock.advance(86400)
    monkeypatch.setattr(sources_catalog, "_SPIKE_RATIO", 1000.0)
    assert store.renormalise("assays", "fake") == 1  # od600 unchanged; only the label differs
    old = store.query("assays", "S1", march(1, 3), as_of=day(10)).frame
    new = store.query("assays", "S1", march(1, 3)).frame
    assert old.loc[old["day"].dt.day == 2, "quality"].item() == "suspect"
    assert new.loc[new["day"].dt.day == 2, "quality"].item() == "ok"
    assert version_count(store) == 4


async def test_changed_value_adds_version_and_as_of_sees_old(
    make_store: MakeStore, clock: FakeClock
) -> None:
    restating = RestatingProvider()
    store = make_store(assays=[restating])
    original = await get(store)
    clock.advance(86400)
    restating.restated_before, restating.spike_days = day(3), {day(2)}
    await get(store, a=1, b=5)  # restates days 1-2; day 2's value changes
    old = store.query("assays", "S1", march(1, 3), as_of=day(10)).frame
    new = store.query("assays", "S1", march(1, 3)).frame
    assert old["od600"].tolist() == original.frame["od600"].tolist()
    assert new.loc[new["day"].dt.day == 2, "od600"].item() > 50
    assert new.loc[new["day"].dt.day != 2, "od600"].tolist() == old.loc[old["day"].dt.day != 2, "od600"].tolist()
    assert version_count(store) == 3 + 2 + 1  # 3 original, 2 new days (4, 5)... plus 1 restated version of day 2


async def test_as_of_excludes_later_known_at(make_store: MakeStore, clock: FakeClock) -> None:
    store = make_store()
    await get(store, a=1, b=3)
    clock.advance(5 * 86400)
    await get(store, a=6, b=8)
    full = march(1, 8)
    assert days_of(store.query("assays", "S1", full, as_of=day(12))) == [1, 2, 3]
    assert days_of(store.query("assays", "S1", full, as_of=day(10))) == [1, 2, 3]  # end of that UTC day
    assert store.query("assays", "S1", full, as_of=day(9)).frame.empty
    assert days_of(store.query("assays", "S1", full, as_of=day(15))) == [1, 2, 3, 6, 7, 8]
    assert days_of(store.query("assays", "S1", full)) == [1, 2, 3, 6, 7, 8]


async def test_known_at_from_normaliser_wins_over_first_seen(make_store: MakeStore) -> None:
    flagging = FlaggingProvider()
    flagging.publish_lag = timedelta(days=30)  # every row is "published" 30 days after its day
    store = make_store(assays=[flagging])
    slice_ = await get(store)
    assert bool((slice_.frame["known_at"] > slice_.frame["first_seen_at"]).all())
    assert store.query("assays", "S1", march(1, 3), as_of=day(20)).frame.empty
    assert days_of(store.query("assays", "S1", march(1, 3), as_of=date(2026, 4, 1))) == [1, 2]


async def test_rejected_excluded_suspect_served_with_reasons(make_store: MakeStore) -> None:
    flagging = FlaggingProvider()
    flagging.rejected_days = {day(1)}
    flagging.spike_days = {day(3)}
    store = make_store(assays=[flagging])
    default = await get(store)
    assert days_of(default) == [2, 3]
    suspect = default.frame.loc[default.frame["day"].dt.day == 3].iloc[0]
    assert suspect["quality"] == "suspect" and list(suspect["quality_reasons"]) == ["jump_x100"]
    with_rejected = await get(store, include_rejected=True)
    assert days_of(with_rejected) == [1, 2, 3]


async def test_fallback_to_second_provider_on_empty(
    make_store: MakeStore, fake: FakeAssayProvider, bulk: FakeBulkAssayProvider
) -> None:
    fake.unknown = {"S9"}
    store = make_store(assays=[fake, bulk])
    slice_ = await get(store, "S9")
    assert slice_.provider == "fake_bulk" and not slice_.empty and days_of(slice_) == [1, 2, 3]
    assert not slice_.pit_reliable  # bulk declares no PIT reliability
    await get(store, "S9")
    assert (len(fake.calls), len(bulk.calls)) == (1, 1)  # empty is cached for `fake`
    assert [a.kind for a in store.attempts("assays", "S9") if a.provider == "fake"] == ["empty"]


async def test_all_providers_empty_gives_empty_slice(
    make_store: MakeStore, fake: FakeAssayProvider, bulk: FakeBulkAssayProvider
) -> None:
    fake.unknown = bulk.unknown = {"S9"}
    store = make_store(assays=[fake, bulk])
    slice_ = await get(store, "S9")
    assert slice_.empty and slice_.provider is None and not slice_.pit_reliable
    assert slice_.frame.empty
    assert {"day", "od600", *FACT_META_COLUMNS} <= set(slice_.frame.columns)
    await get(store, "S9")
    assert (len(fake.calls), len(bulk.calls)) == (1, 1)


async def test_known_empty_still_serves_stored_facts(
    make_store: MakeStore, fake: FakeAssayProvider, bulk: FakeBulkAssayProvider, clock: FakeClock
) -> None:
    store = make_store(assays=[fake, bulk])
    await get(store, a=1, b=3)
    fake.unknown = {"S1"}
    clock.advance(86400)
    widened = await get(store, a=1, b=6)  # fake is asked for the gap and answers `empty`
    assert widened.provider == "fake" and days_of(widened) == [1, 2, 3]
    clock.advance(86400)
    calls = len(fake.calls)
    again = await get(store, a=1, b=3)  # within empty_ttl: nothing is called
    assert len(fake.calls) == calls and bulk.calls == []
    assert again.provider == "fake" and days_of(again) == [1, 2, 3]


async def test_error_raises_source_unavailable_and_is_not_cached(
    make_store: MakeStore, fake: FakeAssayProvider
) -> None:
    fake.script["S1"] = ["error", "error", "error"]  # 1 try + 2 retries
    store = make_store()
    with pytest.raises(SourceUnavailable, match=r"assays.*S1.*fake|fake.*assays.*S1"):
        await get(store)
    assert len(fake.calls) == 3
    assert store.coverage("assays", "S1", "fake").is_empty() and version_count(store) == 0
    assert days_of(await get(store)) == [1, 2, 3]  # the script is exhausted: this one succeeds
    assert [a.kind for a in store.attempts("assays", "S1")] == ["error", "ok"]


async def test_global_failure_keeps_finished_items_and_resumes(
    make_store: MakeStore, fake: FakeAssayProvider, tmp_path: Path
) -> None:
    path = tmp_path / "source.duckdb"
    entities = ["S1", "S2", "S3", "S4"]
    serial = {"fake": RateLimitPolicy(concurrency=1, max_unreachable=0)}
    first = make_store(path=path, policy_overrides=serial)
    fake.script["S3"] = ["unreachable"]
    with pytest.raises(GlobalFailure):
        await first.ensure("assays", entities, march(1, 3))
    first.close()
    fake.calls.clear()
    fake.script.clear()
    second = make_store(path=path)
    assert second.coverage("assays", "S1", "fake").covers(march(1, 3))
    await second.ensure("assays", entities, march(1, 3))
    assert sorted(c[0].entity for c in fake.calls) == ["S3", "S4"]


async def test_ensure_batches_by_max_batch(make_store: MakeStore, bulk: FakeBulkAssayProvider) -> None:
    store = make_store(assays=[bulk])
    await store.ensure("assays", [f"S{i}" for i in range(7)], march(1, 3))
    assert sorted(len(c) for c in bulk.calls) == [2, 5]


async def test_restated_before_refetches_history_in_same_get(
    make_store: MakeStore, clock: FakeClock
) -> None:
    restating = RestatingProvider()
    store = make_store(assays=[restating])
    await get(store, a=1, b=3)
    clock.advance(86400)
    restating.restated_before, restating.spike_days = day(3), {day(2)}
    restating.calls.clear()
    slice_ = await get(store, a=1, b=5)
    assert [c[0].interval for c in restating.calls] == [march(4, 5), march(1, 2)]
    assert days_of(slice_) == [1, 2, 3, 4, 5]
    assert slice_.frame.loc[slice_.frame["day"].dt.day == 2, "od600"].item() > 50


async def test_snapshot_refetched_after_ttl(
    make_store: MakeStore, fake: FakeAssayProvider, clock: FakeClock
) -> None:
    store = make_store()
    first = await store.get("strain_info", "S1")
    assert first.frame["label"].tolist() == ["strain S1"]
    clock.advance(89 * 86400)
    await store.get("strain_info", "S1")
    assert len(fake.calls) == 1
    clock.advance(2 * 86400)
    await store.get("strain_info", "S1")
    assert len(fake.calls) == 2


async def test_offline_serves_covered_and_raises_on_gap(
    make_store: MakeStore, fake: FakeAssayProvider, clock: FakeClock, tmp_path: Path
) -> None:
    path = tmp_path / "source.duckdb"
    online = make_store(path=path)
    await get(online, a=1, b=3)
    await online.get("strain_info", "S1")
    online.close()
    calls = len(fake.calls)
    offline = make_store(path=path, offline=True)
    assert days_of(await get(offline, a=1, b=3)) == [1, 2, 3]
    with pytest.raises(SourceUnavailable):
        await get(offline, a=1, b=5)
    with pytest.raises(SourceUnavailable):
        await get(offline, "S2")
    clock.advance(91 * 86400)
    with pytest.raises(SourceUnavailable):  # a due snapshot is a gap too
        await offline.get("strain_info", "S1")
    assert len(fake.calls) == calls


async def test_renormalise_rebuilds_without_fetch(
    make_store: MakeStore, fake: FakeAssayProvider, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.spike_days = {day(3)}
    store = make_store()
    original = await get(store, a=1, b=5)
    assert original.frame.loc[original.frame["day"].dt.day == 3, "quality"].item() == "suspect"
    raw_before = store.raw_responses("assays", "fake")
    calls = len(fake.calls)
    clock.advance(86400)
    fake.normaliser_version_value = "2"
    monkeypatch.setattr(sources_catalog, "_SPIKE_RATIO", 1000.0)
    assert store.renormalise("assays", "fake") == 1
    rebuilt = store.query("assays", "S1", march(1, 5)).frame
    spike = rebuilt.loc[rebuilt["day"].dt.day == 3].iloc[0]
    assert (spike["quality"], spike["normaliser_version"]) == ("ok", "2")
    assert rebuilt["od600"].tolist() == original.frame["od600"].tolist()
    assert len(fake.calls) == calls
    assert store.raw_responses("assays", "fake") == raw_before
    (record,) = store.renormalisations()
    assert (record.dataset, record.provider, record.normaliser_version) == ("assays", "fake", "2")
    assert (record.raw_responses_read, record.rows_written) == (1, 1)
    assert record.started_at <= record.finished_at


async def test_policy_override_replaces_declared_policy(
    make_store: MakeStore, fake: FakeAssayProvider
) -> None:
    fake.script["S1"] = ["error"] * 3
    declared = make_store()  # declared max_error_retries = 2: three calls
    with pytest.raises(SourceUnavailable):
        await get(declared)
    assert len(fake.calls) == 3
    fake.calls.clear()
    fake.script["S1"] = ["error"] * 3
    overridden = make_store(policy_overrides={"fake": RateLimitPolicy(max_error_retries=0)})
    with pytest.raises(SourceUnavailable):
        await get(overridden)
    assert len(fake.calls) == 1


async def test_facts_table_columns_are_typed(make_store: MakeStore) -> None:
    store = make_store()
    await get(store)
    types = dict(
        store._con.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'facts_assays'"
        ).fetchall()
    )
    assert types["od600"] == "DOUBLE"
    assert types["day"] in {"DATE", "TIMESTAMP"}
    assert types["repairs"] == types["quality_reasons"] == "VARCHAR[]"
    assert types["known_at"] == types["first_seen_at"] == "TIMESTAMP"


async def test_renormalise_after_restatement_adds_nothing_when_unchanged(
    make_store: MakeStore, clock: FakeClock
) -> None:
    restating = RestatingProvider()
    store = make_store(assays=[restating])
    await get(store, a=1, b=3)
    clock.advance(86400)
    restating.restated_before, restating.spike_days = day(3), {day(2)}
    await get(store, a=1, b=5)  # day 2 restated: two raw responses disagree on it
    latest = store.query("assays", "S1", march(1, 5)).frame
    versions = version_count(store)
    for _ in range(2):
        clock.advance(86400)
        assert store.renormalise("assays", "fake") == 0
    assert version_count(store) == versions
    assert store.query("assays", "S1", march(1, 5)).frame["od600"].tolist() == latest["od600"].tolist()


async def test_query_does_not_fall_through_when_primary_rows_filtered(
    make_store: MakeStore, fake: FakeAssayProvider, bulk: FakeBulkAssayProvider
) -> None:
    flagging = FlaggingProvider()
    flagging.rejected_days = {day(1), day(2), day(3)}
    store = make_store(assays=[flagging, bulk])
    await get(store)
    rejected = store.query("assays", "S1", march(1, 3))
    assert rejected.provider == "fake" and rejected.frame.empty and not rejected.empty
    assert {"day", "od600", *FACT_META_COLUMNS} <= set(rejected.frame.columns)
    early = store.query("assays", "S1", march(1, 3), as_of=day(9), include_rejected=True)
    assert early.provider == "fake" and early.frame.empty
    assert bulk.calls == []


async def test_duplicate_keys_from_normalise_raise(make_store: MakeStore) -> None:
    class Duplicating(FakeAssayProvider):
        def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
            frame = super().normalise(dataset, raw, payload)
            return pd.concat([frame, frame.iloc[:1]], ignore_index=True)

    store = make_store(assays=[Duplicating()])
    with pytest.raises(ValueError, match=r"assays.*fake|fake.*assays"):
        await get(store)
    assert version_count(store) == 0 and store.coverage("assays", "S1", "fake").is_empty()


def latest_seq(store: DuckDBSourceStore, d: int) -> int:
    return store._con.execute(
        "SELECT max(version_seq) FROM facts_assays WHERE day = ?", [datetime(2026, 3, d)]
    ).fetchone()[0]  # type: ignore[index]


async def test_same_instant_versions_ordered_by_version_seq(make_store: MakeStore) -> None:
    restating = RestatingProvider()
    store = make_store(assays=[restating])
    await get(store, a=1, b=3)
    restating.restated_before, restating.spike_days = day(3), {day(2)}
    await get(store, a=1, b=5)  # no clock advance: both versions share first_seen_at
    frame = store.query("assays", "S1", march(2)).frame
    assert frame["od600"].item() > 50
    seqs = store._con.execute(
        "SELECT version_seq FROM facts_assays WHERE day = ? ORDER BY version_seq", [datetime(2026, 3, 2)]
    ).fetchall()
    assert len(seqs) == 2 and seqs[0][0] < seqs[1][0]


async def test_version_seq_survives_reopen(
    make_store: MakeStore, clock: FakeClock, tmp_path: Path
) -> None:
    path = tmp_path / "source.duckdb"
    first = make_store(assays=[RestatingProvider()], path=path)
    await get(first, a=1, b=3)
    before = latest_seq(first, 2)
    first.close()
    clock.advance(86400)
    restating = RestatingProvider()
    restating.restated_before, restating.spike_days = day(3), {day(2)}
    second = make_store(assays=[restating], path=path)
    await get(second, a=1, b=5)
    assert second.query("assays", "S1", march(2)).frame["od600"].item() > 50
    assert latest_seq(second, 2) > before
