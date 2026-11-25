"""Contracts of the source store: intervals, models, clock, toy providers."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from lensgraph.sources import (
    Dataset,
    DateInterval,
    FakeClock,
    FetchOutcome,
    IntervalSet,
    NormalisedMeta,
    Provider,
    SystemClock,
    WorkItem,
)
from pydantic import ValidationError
from toy.sources_catalog import (
    ASSAYS,
    STRAIN_INFO,
    AssaySchema,
    FakeAssayProvider,
    FakeBulkAssayProvider,
    make_raw,
)


def d(day: int) -> date:
    return date(2026, 1, day)


def iv(a: int, b: int) -> DateInterval:
    return DateInterval(start=d(a), end=d(b))


def test_interval_rejects_reversed() -> None:
    with pytest.raises(ValidationError):
        iv(5, 1)


def test_interval_set_merges_overlap_and_adjacent_days() -> None:
    assert IntervalSet(intervals=(iv(1, 3), iv(4, 5))).intervals == (iv(1, 5),)
    assert IntervalSet(intervals=(iv(4, 6), iv(1, 5))).intervals == (iv(1, 6),)
    assert IntervalSet(intervals=(iv(1, 3), iv(6, 7))).intervals == (iv(1, 3), iv(6, 7))


def test_interval_set_subtract_leaves_middle_hole_pair() -> None:
    result = IntervalSet(intervals=(iv(1, 10),)).subtract(iv(4, 6))
    assert result.intervals == (iv(1, 3), iv(7, 10))
    assert IntervalSet(intervals=(iv(1, 5),)).subtract(iv(1, 9)).is_empty()


def test_interval_set_covers_and_intersect() -> None:
    s = IntervalSet(intervals=(iv(1, 5), iv(8, 10)))
    assert s.covers(iv(2, 4))
    assert not s.covers(iv(4, 9))
    assert s.intersect(iv(3, 9)).intervals == (iv(3, 5), iv(8, 9))
    assert s.intersect(IntervalSet(intervals=(iv(6, 7),))).is_empty()
    assert s.last_day() == d(10)
    assert IntervalSet().last_day() is None


def test_interval_set_union() -> None:
    assert IntervalSet(intervals=(iv(1, 2),)).union(iv(3, 4)).intervals == (iv(1, 4),)


def test_dataset_date_axis_requires_axis_column() -> None:
    with pytest.raises(ValidationError):
        Dataset(
            name="x",
            frame_schema=AssaySchema,
            key_columns=("day",),
            axis="date",
            ttl=timedelta(days=1),
            empty_ttl=timedelta(days=1),
        )


def test_outcome_ok_requires_payload() -> None:
    item = WorkItem(dataset="assays", entity="S1", interval=iv(1, 2))
    with pytest.raises(ValidationError):
        FetchOutcome(item=item, kind="ok")
    assert FetchOutcome(item=item, kind="empty").payload is None


async def test_fake_clock_sleep_advances_time() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    await clock.sleep(30)
    clock.advance(60)
    assert clock.sleeps == [30]
    assert clock.now() == datetime(2026, 1, 1, 0, 1, 30, tzinfo=UTC)
    assert SystemClock().now().tzinfo is not None


def test_fake_providers_satisfy_protocol_and_differ() -> None:
    single, bulk = FakeAssayProvider(), FakeBulkAssayProvider()
    assert isinstance(single, Provider) and isinstance(bulk, Provider)
    assert (single.name, bulk.name) == ("fake", "fake_bulk")
    assert single.capabilities.max_batch == 1 and bulk.capabilities.max_batch == 5
    assert single.capabilities.rate_limit != bulk.capabilities.rate_limit


def test_fake_provider_fetch_script_unknown_and_settled() -> None:
    p = FakeAssayProvider()
    p.script["S1"] = ["rate_limited"]
    p.unknown.add("GONE")
    p.settled_through = d(3)
    items = [WorkItem(dataset="assays", entity=e, interval=iv(1, 5)) for e in ("S1", "GONE")]
    first = p.fetch(ASSAYS, items)
    assert [o.kind for o in first] == ["rate_limited", "empty"]
    second = p.fetch(ASSAYS, items[:1])[0]
    assert second.kind == "ok" and second.settled_through == d(3) and len(second.payload) == 5
    assert len(p.calls) == 2
    info = p.fetch(STRAIN_INFO, [WorkItem(dataset="strain_info", entity="S1", interval=None)])
    assert info[0].kind == "ok"


def test_fake_provider_normalise_marks_spike_suspect() -> None:
    p = FakeAssayProvider()
    p.spike_days = {d(3)}
    item = WorkItem(dataset="assays", entity="S1", interval=iv(1, 5))
    outcome = p.fetch(ASSAYS, [item])[0]
    frame = p.normalise(ASSAYS, make_raw(), outcome.payload)
    by_day: pd.DataFrame = frame.set_index(frame["day"].dt.day)
    assert by_day.loc[3, "quality"] == "suspect"
    assert by_day.loc[3, "quality_reasons"] == ["jump_x100"]
    others = by_day.drop(index=3)
    assert set(others["quality"]) == {"ok"}
    assert all(r == [] for r in list(others["repairs"]))
    meta = frame[["repairs", "quality", "quality_reasons"]]
    NormalisedMeta.validate(pd.DataFrame(meta))


def test_normalise_marks_non_positive_rejected() -> None:
    p = FakeAssayProvider()
    payload = pd.DataFrame({"t": ["2026-01-01", "2026-01-02"], "value": [1.0, -1.0]})
    frame = p.normalise(ASSAYS, make_raw(), payload)
    assert list(frame["quality"]) == ["ok", "rejected"]
