---
id: TASK-27
title: 'M4.2 Source coverage planning: gaps, settled tail, TTL and empty caching'
status: In Review
assignee: []
created_date: '2026-11-25T01:09:15Z'
updated_date: '2026-11-25T02:56:13Z'
labels:
  - core
milestone: m-3
dependencies:
  - TASK-26
references:
  - documentation/design/core.md
type: feature
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Pure coverage logic: given what the store knows about one (dataset, entity, provider, params), decide what to fetch, and fold an outcome back in. No I/O, no asyncio. Parallel with M4.3 and M4.4. Spec: `documentation/design/core.md`, Source store (Coverage, Fetch-attempt log, TTL, Settled data only); `documentation/design/lessons.md` (the alpha-capture coverage bugs this must not repeat).

TTL semantics (decided in planning, 2026-11-25; write them into core.md in this task):
- Settled coverage on a date axis **never expires**. Settled history changes only through `restated_before` (the provider says earlier facts changed) or `renormalise`.
- `Dataset.ttl` governs the **unsettled tail** (requested days after the last settled day) and **snapshots** (axis "none").
- `Dataset.empty_ttl` governs `empty` outcomes. `error`, `rate_limited` and `unreachable` change nothing (never cached).

## Files
- Create: `packages/lensgraph/src/lensgraph/sources/coverage.py`
- Modify: `documentation/design/core.md` (Source store: replace "TTL per dataset …" bullet with the semantics above)
- Test: `packages/lensgraph/tests/test_source_coverage.py`

## Interfaces
Consumes: `DateInterval`, `IntervalSet`, `Dataset`, `FetchOutcome`, `WorkItem` (M4.1); toy `ASSAYS`, `STRAIN_INFO`.

Produces:
```python
class CoverageState(BaseModel):        # frozen; one per (dataset, entity, provider, params)
    settled: IntervalSet = IntervalSet()   # requested days successfully fetched, clipped to the settled point
    settled_through: date | None = None    # latest settled day the provider has reported
    tail_checked_at: datetime | None = None  # last ok fetch whose request reached past settled_through
    snapshot_at: datetime | None = None    # axis "none": last ok fetch
    empty_at: datetime | None = None       # last `empty` outcome
class GapPlan(BaseModel):              # frozen
    gaps: tuple[DateInterval, ...] = ()    # axis "date": intervals to fetch, sorted, merged
    snapshot_due: bool = False             # axis "none": fetch the snapshot
    known_empty: bool = False              # a fresh `empty` outcome; fetch nothing, serve empty
    def is_fresh(self) -> bool             # nothing to fetch and not known_empty
def plan_gaps(dataset: Dataset, state: CoverageState, requested: DateInterval | None, now: datetime) -> GapPlan
def apply_outcome(dataset: Dataset, state: CoverageState, outcome: FetchOutcome, now: datetime) -> CoverageState
```
Semantics:
- `plan_gaps`, axis "date": `gaps = requested − settled`. The part of a gap after `settled_through` is the tail: dropped when `tail_checked_at` is within `ttl` of `now`, kept otherwise. A fresh `empty_at` (within `empty_ttl`) gives `known_empty=True` and no gaps.
- `plan_gaps`, axis "none": `snapshot_due` when `snapshot_at` is None or older than `ttl`; `requested` must be None (ValueError otherwise).
- `apply_outcome` ok, axis "date": `settled ∪= item.interval ∩ [.., settled_through]` (the *requested* range, not the returned rows; weekends are not gaps); `settled_through = max(old, outcome.settled_through)`; `tail_checked_at = now` if the request reached past it; clears `empty_at`. A missing `settled_through` on a date-axis ok outcome is a ValueError (providers must report it).
- `apply_outcome` ok, axis "none": `snapshot_at = now`, clears `empty_at`.
- `restated_before = d`: `settled = settled − [date.min .. d-1]` before the union, so the next plan refetches that history.
- `empty`: `empty_at = now`. `error`/`rate_limited`/`unreachable`: state returned unchanged.

## Steps
- [ ] Write the failing tests in `test_source_coverage.py`:
  - `test_first_request_is_one_gap`
  - `test_mid_range_hole_is_its_own_gap`: settled [1..10] and [20..30], request [1..30] → gap [11..19] only.
  - `test_union_not_overwrite`: two outcomes for [1..5] then [10..15] leave both covered.
  - `test_short_fetch_does_not_block_longer_request`: the alpha-capture bug. A 30-day fetch, then a 365-day request at the same `now` → gap is the earlier 335 days.
  - `test_weekend_inside_request_is_not_a_gap`: coverage is the requested range even if the payload has no weekend rows.
  - `test_settled_history_never_expires`: two years later, the settled part plans no gap.
  - `test_unsettled_tail_fresh_then_stale`: tail skipped within ttl, planned after it.
  - `test_rows_after_settled_not_covered`: ok outcome for [1..10] with settled_through 8 → settled ends at 8.
  - `test_empty_cached_for_empty_ttl_then_retried`
  - `test_error_and_rate_limit_change_nothing`
  - `test_restated_before_drops_earlier_coverage`
  - `test_snapshot_due_after_ttl`, `test_snapshot_rejects_interval`
  - `test_date_ok_without_settled_through_raises`
- [ ] Run `uv run pytest packages/lensgraph/tests/test_source_coverage.py -q`. Expected: FAIL.
- [ ] Implement; update core.md.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): source coverage planning (interval sets, TTL, settled tail)`.

Out of scope: storage of states and attempts (M4.5), scheduling (M4.3).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 plan_gaps returns only missing intervals, including mid-range holes; a short earlier fetch never blocks a longer request
- [ ] #2 Settled history never expires; the unsettled tail and snapshots follow ttl; empty outcomes follow empty_ttl; errors change nothing
- [ ] #3 apply_outcome records requested ranges clipped to settled_through and honours restated_before
- [ ] #4 core.md Source store states the TTL semantics
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_576944040993, worktree task-27
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: lensgraph/sources/coverage.py (CoverageState, GapPlan, plan_gaps, apply_outcome), 20 tests, core.md TTL bullet replaced. 1 commit b5cf22d. pytest 364 passed, ruff and pyright clean (re-run by coordinator).
Worker rulings: a request wholly inside settled history leaves tail_checked_at unchanged; settled_through never moves backwards; an ok outcome wholly past settled_through adds no coverage; plan_gaps raises ValueError for a date axis without an interval; restated_before=date.min is a no-op; empty is cached for snapshots too.
Coordinator review: approve, no fix round. Matches Interfaces and semantics exactly; docstrings fine.
Open point (spec-level, for the human / TASK-30): empty_at is one scalar per (dataset, entity, provider, params). An `empty` for one date range (e.g. a no-news window or an unsettled tail day) makes plan_gaps return known_empty for ANY request within empty_ttl, including ranges already settled. TASK-30 must not "serve empty" over settled facts; either the store serves stored facts when known_empty, or empty should be recorded per interval.
<!-- SECTION:FINAL_SUMMARY:END -->
