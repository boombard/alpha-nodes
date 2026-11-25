---
id: TASK-41
title: 'Source store: held empty outcomes are persisted under another call''s dataset'
status: In Review
assignee: []
created_date: '2026-11-25T05:45:08Z'
updated_date: '2026-11-25T05:58:34Z'
labels:
  - lensgraph
dependencies: []
references:
  - documentation/design/core.md
priority: high
type: feature
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`ProviderLimiter` is shared by every `ensure` call on a provider, across datasets, and it holds `empty` outcomes while an empty streak is open (TASK-36 breakers). The held outcomes are handed over through whichever call's `on_outcome` / `on_tripped` flushes them, not the call that fetched them. When `prices` and `fx` (or `profile`) fetch concurrently on yfinance, a `prices` empty for an unknown ticker gets persisted by the `fx` call's `persist` closure: the attempt and the coverage row are written under `fx`, nothing is written under `prices`, and `prices` refetches the unknown ticker on every run. Found as the flaky `packages/alpha_nodes/tests/test_m4_e2e.py::test_unknown_ticker_is_empty_not_failure` (about 2 failures in 15 runs on main at 5f6095b): the failing run's attempt log had `('fx', 'NOSUCH.L', 'empty', 'HTTP Error 404: ')` and no `prices` attempt. Spec: `documentation/design/core.md` (Source store: provider scheduler, circuit breakers).

The same mix-up affects `run_items`' final `limiter.flush(on_outcome)` (it flushes other calls' held empties through this call's callback), `take_held` on failure (another call's empties get logged through this call's `on_tripped`), and, within one dataset, normalise failures being collected in another call's `normalise_failures` list.

## Files
- Modify: `packages/lensgraph/src/lensgraph/sources/scheduler.py` (`ProviderLimiter.settle/flush/take_held`, `run_items`), `documentation/design/core.md` if the breaker description needs it
- Test: `packages/lensgraph/tests/test_source_scheduler.py`, `packages/lensgraph/tests/test_source_store.py`

## Behaviour
- Each held outcome keeps the `on_outcome` / `on_tripped` of the call that produced it, and is handed over through those, whichever call ends the streak.
- The streak itself stays provider-wide (counting distinct entities across datasets), as the breaker intends.
- When a breaker trips in one call, the other calls' held empties are logged through their own `on_tripped`.

## Steps
- [ ] Failing scheduler test: two concurrent `run_items` calls on one limiter with different callbacks; call A's empty is held, call B's ok ends the streak; A's empty must reach A's callback, not B's. Same for the final flush and for a trip.
- [ ] Failing store test with a toy provider serving two datasets concurrently (`asyncio.gather` of two `ensure` calls): an empty on dataset X is logged and cached under X.
- [ ] Implement: hold `(outcome, on_outcome, on_tripped)` entries.
- [ ] Rerun `uv run pytest packages/alpha_nodes/tests/test_m4_e2e.py -k unknown` 30 times in a loop: no failures.
- [ ] `uv run pytest -q`, ruff, pyright.
- [ ] Commit: `fix(lensgraph): hand held empty outcomes to the call that fetched them`.

Out of scope: changing breaker thresholds or streak semantics.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A held empty outcome is handed to the on_outcome/on_tripped of the call that fetched it, for streak ends, the final flush and breaker trips
- [ ] #2 Concurrent ensure calls on two datasets of one provider log and cache an empty under its own dataset (store test)
- [ ] #3 test_m4_e2e unknown-ticker test passes 30 runs in a row
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
Worker: dispatch ctx_9a326584f5c7, worktree task-41
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: ProviderLimiter holds (outcome, on_outcome, on_tripped) entries; a streak end, the final flush and a breaker trip hand each held empty to the call that fetched it (streak still provider-wide). Review round: a failing or cancelled call now takes back only its own held empties (take_held(owner=on_outcome)); other calls' stay held. core.md Circuit breakers updated. Commits ef79107, 1fd6b80; tests: 6 scheduler tests (streak end, final flush, trip, own-failure, other call failing, other call cancelled) and a concurrent two-dataset store test that failed before the fix; pytest 637 passed, ruff and pyright clean; test_m4_e2e -k unknown 30/30. Coordinator review: ACs met after one fix round, nothing open. Rulings: limiter.flush() takes no argument (module-internal); call ownership is the identity of the call's on_outcome closure (one per ensure pass and provider); the old failed-run scheduler test was rewritten because it encoded the cross-call behaviour.
<!-- SECTION:FINAL_SUMMARY:END -->
