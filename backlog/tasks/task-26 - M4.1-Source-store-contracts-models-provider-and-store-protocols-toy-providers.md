---
id: TASK-26
title: >-
  M4.1 Source store contracts: models, provider and store protocols, toy
  providers
status: Done
assignee: []
created_date: '2026-11-25T01:09:15Z'
updated_date: '2026-11-25T02:50:58Z'
labels:
  - core
  - contracts
milestone: m-3
dependencies:
  - TASK-11
references:
  - documentation/design/core.md
type: feature
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Contracts task for M4. Sequential: every other M4 task builds on these names. Spec: `documentation/design/core.md`, Source store (layer 1 cache); `documentation/design/lessons.md` (caching lessons). Global constraints: `backlog/docs/doc-1 - Implementation-plan.md`. lensgraph only: nothing here may mention finance (no tickers, prices, currencies).

## Files
- Create:
  - `packages/lensgraph/src/lensgraph/sources/__init__.py` (exports)
  - `packages/lensgraph/src/lensgraph/sources/models.py`: the models below
  - `packages/lensgraph/src/lensgraph/sources/base.py`: `Provider`, `SourceStore`, `Clock` protocols; `SourceUnavailable`
  - `packages/lensgraph/src/lensgraph/sources/clock.py`: `SystemClock`, `FakeClock`
  - `packages/lensgraph/tests/toy/sources_catalog.py`: toy datasets and two fake providers
- Modify: `packages/lensgraph/src/lensgraph/__init__.py` (re-export the `sources` names other packages need)
- Test: `packages/lensgraph/tests/test_source_models.py`

## Interfaces
Consumes: `GlobalFailure` (types.py), `BlobStore` (store/base.py; only named in docstrings here).

Produces:
```python
# sources/models.py  (frozen=True, extra="forbid" unless noted)
class DateInterval(BaseModel):          # closed: both ends included; start <= end (ValueError otherwise)
    start: date; end: date
class IntervalSet(BaseModel):           # normalised on construction: sorted, overlapping AND adjacent days merged
    intervals: tuple[DateInterval, ...] = ()
    def union(self, other: "IntervalSet | DateInterval") -> "IntervalSet"
    def subtract(self, other: "IntervalSet | DateInterval") -> "IntervalSet"
    def intersect(self, other: "IntervalSet | DateInterval") -> "IntervalSet"
    def covers(self, interval: DateInterval) -> bool
    def is_empty(self) -> bool
    def last_day(self) -> date | None
class Dataset(BaseModel):               # arbitrary_types_allowed (frame_schema is a class)
    name: str
    frame_schema: type[pa.DataFrameModel]   # canonical columns only (no fact meta columns)
    key_columns: tuple[str, ...]            # identify one fact within an entity, e.g. ("date",); () for a snapshot
    axis: Literal["date", "none"]           # "none" = snapshot data (one current row set per entity)
    axis_column: str | None = None          # required when axis == "date"
    ttl: timedelta                          # freshness of snapshots and of the unsettled tail
    empty_ttl: timedelta                    # how long an `empty` outcome suppresses refetching
class RateLimitPolicy(BaseModel):
    concurrency: int = 1; per_second: float | None = None; burst: int = 1
    backoff_s: tuple[float, ...] = (30.0, 60.0, 120.0, 240.0)   # provider-wide pause per consecutive rate-limit episode
    jitter: float = 0.1                     # fraction of each pause added at random
    max_rate_limit_episodes: int = 3        # consecutive episodes before GlobalFailure
    max_unreachable: int = 5                # consecutive unreachable outcomes before GlobalFailure
    max_error_retries: int = 2              # retries of a transient `error` item before giving up on it
class ProviderCapabilities(BaseModel):
    datasets: frozenset[str]
    max_batch: int = 1                      # entities per provider call; 1 = no batching
    rate_limit: RateLimitPolicy
    pit_reliable: dict[str, bool] = {}      # per dataset; missing = False
class WorkItem(BaseModel):
    dataset: str; entity: str
    interval: DateInterval | None           # None for axis="none"
    params: dict[str, str] = {}
OutcomeKind = Literal["ok", "empty", "error", "rate_limited", "unreachable"]
class FetchOutcome(BaseModel):          # not frozen; arbitrary_types_allowed
    item: WorkItem; kind: OutcomeKind
    payload: Any = None                     # BlobStore-encodable (frame, model, JSON); required when kind == "ok"
    settled_through: date | None = None     # axis="date": last settled day; later rows are not facts
    restated_before: date | None = None     # provider says stored facts before this day changed (e.g. a new split)
    message: str = ""
class RawResponse(BaseModel):           # one stored provider response; immutable
    raw_id: str; provider: str; dataset: str; entity: str
    interval: DateInterval | None; params: dict[str, str] = {}
    payload_hash: str                       # BlobStore hash of the verbatim payload
    fetched_at: datetime; library_version: str
AttemptKind = OutcomeKind | Literal["unsettled"]
class FetchAttempt(BaseModel):
    provider: str; dataset: str; entity: str
    interval: DateInterval | None; params: dict[str, str] = {}
    kind: AttemptKind; at: datetime; message: str = ""
Quality = Literal["ok", "suspect", "rejected"]
class NormalisedMeta(pa.DataFrameModel):   # columns Provider.normalise must add next to the canonical ones
    repairs: object            # list[str] per row, e.g. ["minor_unit"]; [] when none
    quality: str               # one of Quality (pa.Check.isin)
    quality_reasons: object    # list[str]; non-empty when quality != "ok"
    known_at: Optional[...]    # optional column (pandera Optional), tz-aware UTC; the store fills first_seen_at when absent
FACT_META_COLUMNS: tuple[str, ...]  # columns the store adds: entity, provider, fetch_id, first_seen_at,
                                    # known_at, normaliser_version, repairs, quality, quality_reasons
class SourceSlice(BaseModel):           # arbitrary_types_allowed
    dataset: str; entity: str
    provider: str | None                    # who served it; None when empty
    frame: pd.DataFrame                     # canonical + FACT_META_COLUMNS, sorted by key columns
    pit_reliable: bool
    empty: bool                             # True for a legitimate empty (unknown entity, no data)
# sources/base.py
class SourceUnavailable(Exception): ...     # offline gap, or an `error` outcome after retries; the fetch node fails
class Clock(Protocol):
    def now(self) -> datetime: ...          # tz-aware UTC
    async def sleep(self, seconds: float) -> None: ...
class Provider(Protocol):
    name: str
    capabilities: ProviderCapabilities
    library_version: str
    def normaliser_version(self, dataset: str) -> str: ...
    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]: ...  # sync, blocking I/O; one outcome per item, same order; may raise GlobalFailure
    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame: ...  # canonical + NormalisedMeta columns
class SourceStore(Protocol):
    async def get(self, dataset: str, entity: str, interval: DateInterval | None = None, *,
                  as_of: date | None = None, params: Mapping[str, str] = {}, include_rejected: bool = False) -> SourceSlice: ...
    async def ensure(self, dataset: str, entities: Sequence[str], interval: DateInterval | None = None, *,
                     params: Mapping[str, str] = {}) -> None: ...      # fill gaps for many entities (batched)
    def query(self, dataset: str, entity: str, interval: DateInterval | None = None, *,
              as_of: date | None = None, params: Mapping[str, str] = {}, include_rejected: bool = False) -> SourceSlice: ...  # never fetches
    def renormalise(self, dataset: str, provider: str) -> int: ...  # facts rebuilt from raw; returns rows written
    def attempts(self, dataset: str | None = None, entity: str | None = None) -> list[FetchAttempt]: ...
    def coverage(self, dataset: str, entity: str, provider: str, params: Mapping[str, str] = {}) -> IntervalSet: ...
# sources/clock.py
class SystemClock: ...                      # Clock over datetime.now(UTC) and asyncio.sleep
class FakeClock:                            # Clock for tests and replays
    def __init__(self, start: datetime) -> None
    sleeps: list[float]                     # every sleep requested, in order
    def advance(self, seconds: float) -> None
    # sleep() advances time by `seconds` and returns at once (await asyncio.sleep(0) to yield)
# tests/toy/sources_catalog.py
ASSAYS: Dataset            # axis "date" on `day`; columns day (datetime64 midnight), od600 (float > 0); ttl 1 day, empty_ttl 7 days
STRAIN_INFO: Dataset       # axis "none"; columns label (str), lab (str); ttl 90 days, empty_ttl 7 days
class FakeAssayProvider:   # Provider; max_batch=1, RateLimitPolicy(concurrency=2, per_second=10, burst=2)
class FakeBulkAssayProvider:   # Provider; max_batch=5, a different policy (concurrency=1, per_second=1, burst=1)
    # both: name set in __init__ (default "fake"/"fake_bulk"), deterministic data from the entity name,
    # `calls: list[list[WorkItem]]` (one entry per fetch call), `script: dict[str, list[OutcomeKind]]`
    # (entity -> kinds to return on successive calls before falling back to "ok"),
    # `unknown: set[str]` (entities answered "empty"), `settled_through: date | None`,
    # `normaliser_version_value: str`, and `spike_days: set[date]` (od600 x100 on those days; the
    # normaliser marks a x100 day-over-day jump "suspect" with reason "jump_x100", and od600 <= 0 "rejected").
```

## Steps
- [ ] Write the failing tests in `test_source_models.py`:
  - `test_interval_rejects_reversed`
  - `test_interval_set_merges_overlap_and_adjacent_days`: [1..3] ∪ [4..5] is one interval; [1..3] ∪ [6..7] stays two.
  - `test_interval_set_subtract_leaves_middle_hole_pair`: [1..10] − [4..6] = [1..3], [7..10].
  - `test_interval_set_covers_and_intersect`
  - `test_dataset_date_axis_requires_axis_column`
  - `test_outcome_ok_requires_payload`
  - `test_fake_clock_sleep_advances_time`
  - `test_fake_providers_satisfy_protocol_and_differ`: both are `Provider`s (structural check of attributes); max_batch and policy differ.
  - `test_fake_provider_normalise_marks_spike_suspect`: a payload with a spike day gives that row quality "suspect", reasons ["jump_x100"]; other rows "ok", repairs [].
- [ ] Run `uv run pytest packages/lensgraph/tests/test_source_models.py -q`. Expected: FAIL.
- [ ] Implement. Fake providers' payload is a DataFrame (raw columns `t`, `value`), so normalise really maps columns.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): M4 contracts: source store models, provider and store protocols, toy providers`.

Out of scope: gap planning (M4.2), scheduling and limiting (M4.3), the DuckDB store (M4.5), the fetch node and run wiring (M4.8).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 DateInterval and IntervalSet normalise, merge adjacent days and support union/subtract/intersect/covers
- [x] #2 Dataset, RateLimitPolicy, ProviderCapabilities, WorkItem, FetchOutcome, RawResponse, FetchAttempt, NormalisedMeta and SourceSlice match Interfaces
- [x] #3 Provider, SourceStore and Clock protocols, SourceUnavailable, SystemClock and FakeClock exist and are exported
- [x] #4 Two toy fake providers with different max_batch and policies satisfy Provider; the normaliser marks x100 spikes suspect
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run pytest` passes (whole workspace)
- [x] #2 `uv run ruff check` and `uv run pyright` are clean
- [x] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [x] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_450a25a0e6f9, worktree task-26
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: lensgraph.sources contracts (models, Provider/SourceStore/Clock protocols, SourceUnavailable, SystemClock/FakeClock), toy ASSAYS/STRAIN_INFO datasets and FakeAssayProvider/FakeBulkAssayProvider, tests. Branch task-26: 240dbaa, cbd3657. pytest 342 passed, ruff clean, pyright 0 errors. Coordinator review: ACs 1-4 met. One fix round, all applied: SourceSlice and Dataset now frozen via _FROZEN_ARBITRARY; NormalisedMeta.quality derived from Quality; toy fetch returns rows through interval.end and reports settled_through separately; tests use a real RawResponse (make_raw); missing docstring added. Open points: rulings to confirm (toy spike ratio >= 50 is suspect, od600 <= 0 is rejected with reason non_positive; NormalisedMeta non-strict with nullable optional known_at, which M4.5 may tighten; Provider is runtime_checkable). Models were written before the tests, not test-first. The code-review skill was not run; the 806-line diff was reviewed by hand.

Landed 6a8b065..2fb6115 on main (rebased onto e1eefdd; 342 passed, ruff and pyright clean on main).
<!-- SECTION:FINAL_SUMMARY:END -->
