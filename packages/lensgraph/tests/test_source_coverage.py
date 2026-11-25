"""Pure coverage planning: gaps, settled tail, TTL, empty caching."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from lensgraph.sources import DateInterval, FetchOutcome, IntervalSet, WorkItem
from lensgraph.sources.coverage import CoverageState, GapPlan, apply_outcome, plan_gaps
from toy.sources_catalog import ASSAYS, STRAIN_INFO

NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)
BASE = date(2026, 1, 1)


def d(day: int) -> date:
    return BASE + timedelta(days=day - 1)


def iv(a: int, b: int) -> DateInterval:
    return DateInterval(start=d(a), end=d(b))


def item(interval: DateInterval | None, dataset: str = "assays") -> WorkItem:
    return WorkItem(dataset=dataset, entity="S1", interval=interval)


def ok(
    interval: DateInterval, settled_through: date | None, restated_before: date | None = None
) -> FetchOutcome:
    return FetchOutcome(
        item=item(interval),
        kind="ok",
        payload=pd.DataFrame(),
        settled_through=settled_through,
        restated_before=restated_before,
    )


def kind(k: str, interval: DateInterval | None = None, dataset: str = "assays") -> FetchOutcome:
    return FetchOutcome(item=item(interval, dataset), kind=k)  # type: ignore[arg-type]


def test_first_request_is_one_gap() -> None:
    plan = plan_gaps(ASSAYS, CoverageState(), iv(1, 30), NOW)
    assert plan.gaps == (iv(1, 30),)
    assert not plan.is_fresh()


def test_mid_range_hole_is_its_own_gap() -> None:
    state = CoverageState(
        settled=IntervalSet(intervals=(iv(1, 10), iv(20, 30))), settled_through=d(30)
    )
    assert plan_gaps(ASSAYS, state, iv(1, 30), NOW).gaps == (iv(11, 19),)


def test_union_not_overwrite() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 5), d(100)), NOW)
    state = apply_outcome(ASSAYS, state, ok(iv(10, 15), d(100)), NOW)
    assert state.settled.covers(iv(1, 5)) and state.settled.covers(iv(10, 15))
    assert plan_gaps(ASSAYS, state, iv(1, 15), NOW).gaps == (iv(6, 9),)


def test_short_fetch_does_not_block_longer_request() -> None:
    end = d(365)
    short = DateInterval(start=end - timedelta(days=29), end=end)
    state = apply_outcome(ASSAYS, CoverageState(), ok(short, end), NOW)
    longer = DateInterval(start=end - timedelta(days=364), end=end)
    plan = plan_gaps(ASSAYS, state, longer, NOW)
    assert plan.gaps == (DateInterval(start=longer.start, end=short.start - timedelta(days=1)),)
    assert (plan.gaps[0].end - plan.gaps[0].start).days + 1 == 335


def test_weekend_inside_request_is_not_a_gap() -> None:
    # Payload rows are irrelevant: the requested range is what is covered.
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 14), d(14)), NOW)
    assert plan_gaps(ASSAYS, state, iv(1, 14), NOW).is_fresh()


def test_settled_history_never_expires() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 10), d(10)), NOW)
    later = NOW + timedelta(days=730)
    assert plan_gaps(ASSAYS, state, iv(1, 10), later).is_fresh()


def test_unsettled_tail_fresh_then_stale() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 10), d(8)), NOW)
    assert state.tail_checked_at == NOW
    assert plan_gaps(ASSAYS, state, iv(1, 10), NOW + ASSAYS.ttl / 2).is_fresh()
    stale = plan_gaps(ASSAYS, state, iv(1, 10), NOW + ASSAYS.ttl + timedelta(seconds=1))
    assert stale.gaps == (iv(9, 10),)


def test_rows_after_settled_not_covered() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 10), d(8)), NOW)
    assert state.settled == IntervalSet(intervals=(iv(1, 8),))
    assert state.settled_through == d(8)


def test_fully_settled_request_leaves_tail_unchecked() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 10), d(10)), NOW)
    assert state.tail_checked_at is None


def test_settled_through_never_moves_back() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 10), d(10)), NOW)
    state = apply_outcome(ASSAYS, state, ok(iv(1, 5), d(5)), NOW)
    assert state.settled_through == d(10)


def test_empty_cached_for_empty_ttl_then_retried() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), kind("empty", iv(1, 10)), NOW)
    cached = plan_gaps(ASSAYS, state, iv(1, 10), NOW + ASSAYS.empty_ttl / 2)
    assert cached.known_empty and cached.gaps == () and not cached.is_fresh()
    retried = plan_gaps(ASSAYS, state, iv(1, 10), NOW + ASSAYS.empty_ttl + timedelta(seconds=1))
    assert not retried.known_empty and retried.gaps == (iv(1, 10),)


def test_ok_clears_empty() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), kind("empty", iv(1, 10)), NOW)
    state = apply_outcome(ASSAYS, state, ok(iv(1, 10), d(10)), NOW)
    assert state.empty_at is None


@pytest.mark.parametrize("k", ["error", "rate_limited", "unreachable"])
def test_error_and_rate_limit_change_nothing(k: str) -> None:
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 5), d(5)), NOW)
    assert apply_outcome(ASSAYS, state, kind(k, iv(6, 10)), NOW) == state


def test_restated_before_drops_earlier_coverage() -> None:
    state = apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 20), d(20)), NOW)
    state = apply_outcome(ASSAYS, state, ok(iv(15, 25), d(25), restated_before=d(10)), NOW)
    assert plan_gaps(ASSAYS, state, iv(1, 25), NOW).gaps == (iv(1, 9),)


def test_restated_before_at_date_min() -> None:
    state = apply_outcome(
        ASSAYS, CoverageState(), ok(iv(1, 5), d(5), restated_before=date.min), NOW
    )
    assert state.settled == IntervalSet(intervals=(iv(1, 5),))


def test_snapshot_due_after_ttl() -> None:
    assert plan_gaps(STRAIN_INFO, CoverageState(), None, NOW) == GapPlan(snapshot_due=True)
    out = FetchOutcome(item=item(None, "strain_info"), kind="ok", payload=pd.DataFrame())
    state = apply_outcome(STRAIN_INFO, CoverageState(), out, NOW)
    assert state.snapshot_at == NOW
    assert plan_gaps(STRAIN_INFO, state, None, NOW + STRAIN_INFO.ttl / 2).is_fresh()
    assert plan_gaps(STRAIN_INFO, state, None, NOW + STRAIN_INFO.ttl * 2).snapshot_due


def test_snapshot_empty_cached() -> None:
    state = apply_outcome(STRAIN_INFO, CoverageState(), kind("empty", None, "strain_info"), NOW)
    assert plan_gaps(STRAIN_INFO, state, None, NOW).known_empty


def test_snapshot_rejects_interval() -> None:
    with pytest.raises(ValueError):
        plan_gaps(STRAIN_INFO, CoverageState(), iv(1, 5), NOW)


def test_date_axis_requires_interval() -> None:
    with pytest.raises(ValueError):
        plan_gaps(ASSAYS, CoverageState(), None, NOW)


def test_date_ok_without_settled_through_raises() -> None:
    with pytest.raises(ValueError):
        apply_outcome(ASSAYS, CoverageState(), ok(iv(1, 5), None), NOW)
