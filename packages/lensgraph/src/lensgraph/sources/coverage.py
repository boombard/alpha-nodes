"""Pure source-coverage planning: what to fetch, and how an outcome updates coverage.

No I/O and no asyncio. The store (M4.5) persists `CoverageState`; the scheduler (M4.3)
turns a `GapPlan` into work items. See documentation/design/core.md, Source store
(Coverage, Fetch-attempt log, TTL, Settled data only).
"""

from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from .models import Dataset, DateInterval, FetchOutcome, IntervalSet

_FROZEN = ConfigDict(frozen=True)
_ONE_DAY = timedelta(days=1)


class CoverageState(BaseModel):
    """What the store knows for one (dataset, entity, provider, params).

    Settled coverage of a date axis never expires; `ttl` governs only the unsettled
    tail and snapshots, `empty_ttl` the `empty` outcomes (core.md, Source store, TTL).
    """

    model_config = _FROZEN

    settled: IntervalSet = IntervalSet()  # requested days fetched, clipped to settled_through
    settled_through: date | None = None  # latest settled day the provider has reported
    tail_checked_at: datetime | None = (
        None  # last ok fetch whose request reached past settled_through
    )
    snapshot_at: datetime | None = None  # axis "none": last ok fetch
    empty_at: datetime | None = None  # last `empty` outcome


class GapPlan(BaseModel):
    """The result of `plan_gaps`: what, if anything, must be fetched."""

    model_config = _FROZEN

    gaps: tuple[DateInterval, ...] = ()  # axis "date": intervals to fetch, sorted, merged
    snapshot_due: bool = False  # axis "none": fetch the snapshot
    known_empty: bool = False  # a fresh `empty` outcome: fetch nothing, serve empty

    def is_fresh(self) -> bool:
        """True when nothing needs fetching and the answer is not a cached empty."""
        return not self.gaps and not self.snapshot_due and not self.known_empty


def _within(at: datetime | None, ttl: timedelta, now: datetime) -> bool:
    return at is not None and now - at <= ttl


def plan_gaps(
    dataset: Dataset, state: CoverageState, requested: DateInterval | None, now: datetime
) -> GapPlan:
    """Decide what to fetch for `requested` (None for snapshot datasets) at `now`.

    Date axis: the requested days not yet settled. The part after `settled_through` is
    the tail and is skipped while `tail_checked_at` is within `dataset.ttl`.
    Snapshot axis: due when never fetched or older than `dataset.ttl`.
    A fresh `empty` outcome (within `dataset.empty_ttl`) short-circuits to `known_empty`.
    """
    if dataset.axis == "none":
        if requested is not None:
            raise ValueError("snapshot datasets (axis='none') take no requested interval")
    elif requested is None:
        raise ValueError("date-axis datasets need a requested interval")

    if _within(state.empty_at, dataset.empty_ttl, now):
        return GapPlan(known_empty=True)

    if requested is None:
        return GapPlan(snapshot_due=not _within(state.snapshot_at, dataset.ttl, now))

    missing = IntervalSet(intervals=(requested,)).subtract(state.settled)
    if state.settled_through is not None and _within(state.tail_checked_at, dataset.ttl, now):
        tail_start = state.settled_through + _ONE_DAY
        if tail_start <= requested.end:
            missing = missing.subtract(DateInterval(start=tail_start, end=requested.end))
    return GapPlan(gaps=missing.intervals)


def apply_outcome(
    dataset: Dataset, state: CoverageState, outcome: FetchOutcome, now: datetime
) -> CoverageState:
    """Fold a fetch outcome into `state`.

    `ok` records the *requested* range (clipped to `settled_through`), honouring
    `restated_before` by first dropping earlier coverage. `empty` is cached via
    `empty_at`. `error`, `rate_limited` and `unreachable` change nothing.
    """
    if outcome.kind == "empty":
        return state.model_copy(update={"empty_at": now})
    if outcome.kind != "ok":
        return state

    if dataset.axis == "none":
        return state.model_copy(update={"snapshot_at": now, "empty_at": None})

    interval = outcome.item.interval
    if interval is None:
        raise ValueError("date-axis outcome needs an interval on its work item")
    if outcome.settled_through is None:
        raise ValueError("a date-axis 'ok' outcome must report settled_through")

    settled = state.settled
    if outcome.restated_before is not None and outcome.restated_before > date.min:
        settled = settled.subtract(
            DateInterval(start=date.min, end=outcome.restated_before - _ONE_DAY)
        )
    through = max(state.settled_through or date.min, outcome.settled_through)
    if interval.start <= through:
        settled = settled.union(DateInterval(start=interval.start, end=min(interval.end, through)))
    return state.model_copy(
        update={
            "settled": settled,
            "settled_through": through,
            "tail_checked_at": now if interval.end > through else state.tail_checked_at,
            "empty_at": None,
        }
    )
