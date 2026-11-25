---
id: TASK-36
title: M4.5b Source-store circuit breakers and normalise failure isolation
status: To Do
assignee: []
created_date: '2026-11-25T04:06:44Z'
labels:
  - core
milestone: m-3
dependencies:
  - TASK-30
references:
  - documentation/design/core.md
type: feature
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two generic defences in the source store, from the 2026-11-25 defensive review of the yfinance downloads: circuit breakers for failures that hit every entity (a provider-side outage that looks like per-entity results), and isolation of normaliser exceptions so one bad payload fails one entity, not the run. After M4.5 (TASK-30). Spec: `documentation/design/core.md`, Source store; update it in this change.

Why:
- A systemic `error` (the provider changed its format, its auth broke) is retried entity by entity: up to `1 + max_error_retries` calls per entity across the whole universe, exactly when an IP block is most likely. Today only rate limits and `unreachable` count towards `GlobalFailure`.
- A mass `empty` (a provider incident, or throttling disguised as "not found") is cached per entity with `empty_ttl`, so top-ups silently stop for that long.
- An exception in `provider.normalise` inside `DuckDBSourceStore`'s per-outcome persist escapes and aborts the whole `ensure` (TASK-30 review, not fixed there).

## Files
- Modify:
  - `packages/lensgraph/src/lensgraph/sources/models.py`: two `RateLimitPolicy` fields
  - `packages/lensgraph/src/lensgraph/sources/scheduler.py`: the breakers (in `ProviderLimiter`/`run_items`)
  - `packages/lensgraph/src/lensgraph/sources/duckdb_store.py`: normalise failure isolation; empty-streak hand-over
  - `documentation/design/core.md`: Source store (breakers, normalise failures)
- Test: `packages/lensgraph/tests/test_source_scheduler.py`, `packages/lensgraph/tests/test_source_store.py`

## Interfaces
Consumes: `RateLimitPolicy`, `ProviderLimiter`, `run_items`, `GlobalFailure`, `FetchOutcome` (M4.1, M4.3); `DuckDBSourceStore` (M4.5); toy fake providers.

Produces:
```python
class RateLimitPolicy(BaseModel):          # existing; two new fields, both off by default
    ...
    max_consecutive_errors: int | None = None   # distinct entities whose final outcome is `error`, in a row, before GlobalFailure
    max_consecutive_empty: int | None = None    # distinct entities answering `empty`, in a row, before GlobalFailure
```
Semantics:
- Streaks are per provider (per `ProviderLimiter`), in completion order. An entity counts once however many retries it took. Any `ok` resets both streaks; `empty` resets the error streak and `error` resets the empty streak. Rate limits and `unreachable` keep their existing thresholds and don't touch these streaks.
- Error breaker: reaching `max_consecutive_errors` raises `GlobalFailure` naming the provider, the streak length and the last error message. Outcomes already handed to `on_outcome` stay (as today).
- Empty breaker: reaching `max_consecutive_empty` raises `GlobalFailure`, and the `empty` outcomes of the tripping streak are **not cached**: those entities stay unknown, so the next run asks again. To make that possible, `empty` outcomes are held back while an empty streak is open and handed to `on_outcome` when a non-empty outcome breaks the streak or the run ends below the threshold. Their attempts are still logged in the attempt log (as `empty`, message noting the breaker) if the store can do so without caching; otherwise say so in the docstring.
- Normalise failure: when `provider.normalise` (or the settled cut / version append) raises for an `ok` outcome, `DuckDBSourceStore` logs an `error` attempt whose message starts `normalise:` (exception type and message, plus the payload hash), caches nothing for that item (no raw-response record, coverage or facts; the blob may stay), does not retry it, and after the provider level finishes raises `SourceUnavailable` naming dataset, entity, provider and the normaliser message. Other entities are persisted as usual.

## Steps
- [ ] Write the failing tests:
  - `test_source_scheduler.py`:
    - `test_consecutive_errors_across_entities_raise_global_failure`
    - `test_retries_of_one_entity_count_once`
    - `test_ok_resets_error_streak`
    - `test_consecutive_empty_trips_global_failure`
    - `test_empty_streak_below_threshold_is_handed_over`
    - `test_breakers_off_by_default`
  - `test_source_store.py`:
    - `test_tripped_empty_streak_not_cached`: a fake answering `empty` for 5 entities with `max_consecutive_empty=3` → `GlobalFailure`; a new store on the same file asks the provider about all of them again.
    - `test_normalise_failure_is_entity_error_not_crash`: one entity's payload makes `normalise` raise; the others are stored; `SourceUnavailable` names the entity and the `normalise:` message; a later `get` refetches it.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_source_scheduler.py packages/lensgraph/tests/test_source_store.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): source-store circuit breakers and normalise failure isolation`.

Out of scope: setting the yfinance values (TASK-37); overlap reconciliation (TASK-38).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Consecutive errors across distinct entities raise GlobalFailure at max_consecutive_errors; retries of one entity count once; ok resets
- [ ] #2 Consecutive empties raise GlobalFailure at max_consecutive_empty and the tripping streak is not cached; shorter streaks are handed over and cached as before
- [ ] #3 Both breakers are off by default, so existing providers behave as before
- [ ] #4 A normalise exception becomes a logged, uncached, unretried entity error raising SourceUnavailable; other entities are persisted
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
