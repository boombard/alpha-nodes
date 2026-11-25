---
id: TASK-28
title: M4.3 Provider scheduler and shared rate limiter
status: To Do
assignee: []
created_date: '2026-11-25T01:09:15Z'
labels:
  - core
milestone: m-3
dependencies:
  - TASK-26
references:
  - documentation/design/core.md
type: feature
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The core's provider scheduler: group work items by the provider's declared `max_batch`, run them through one shared limiter per provider, pause the whole provider on a rate limit, give up with `GlobalFailure` past the declared thresholds, and hand every final outcome to a callback as soon as it exists (so the store can persist it at once). Parallel with M4.2 and M4.4. Spec: `documentation/design/core.md`, Source store (the Provider bullets: declared capabilities, core scheduling). The core assumes nothing provider-specific: tests run the same scenarios against both toy fake providers.

## Files
- Create: `packages/lensgraph/src/lensgraph/sources/scheduler.py`
- Test: `packages/lensgraph/tests/test_source_scheduler.py`

## Interfaces
Consumes: `Provider`, `Dataset`, `WorkItem`, `FetchOutcome`, `RateLimitPolicy`, `Clock`, `FakeClock`, `GlobalFailure` (M4.1, types.py); toy `FakeAssayProvider`, `FakeBulkAssayProvider`, `ASSAYS`.

Produces:
```python
class ProviderLimiter:
    """One per provider per store: concurrency, token-bucket pacing (per_second, burst), provider-wide pause.

    asyncio primitives are created lazily on first use, so the limiter binds to the loop that uses it.
    """
    def __init__(self, provider: str, policy: RateLimitPolicy, clock: Clock, rng: random.Random | None = None) -> None
    def slot(self) -> AbstractAsyncContextManager[None]   # waits for a pause to end, a concurrency slot and a token
    async def report(self, kind: OutcomeKind) -> None
        # rate_limited: if not already paused, starts episode n (n = consecutive episodes so far + 1) and pauses
        #   every slot for backoff_s[min(n-1, last)] * (1 + jitter * rng.random()); episode n > max_rate_limit_episodes
        #   raises GlobalFailure("<provider>: rate limited <n> times in a row").
        # unreachable: consecutive count; > max_unreachable raises GlobalFailure.
        # ok / empty: reset both counters. error: no effect on counters.
async def run_items(
    provider: Provider, dataset: Dataset, items: Sequence[WorkItem], limiter: ProviderLimiter,
    on_outcome: Callable[[FetchOutcome], Awaitable[None]],
) -> list[FetchOutcome]
    # final outcomes (ok / empty / error) in input order
```
Semantics of `run_items`:
- Items are grouped into batches of at most `provider.capabilities.max_batch`, keeping only items with equal `params` together. Each batch is one `provider.fetch` call, run with `asyncio.to_thread` inside `limiter.slot()`.
- Per outcome: `rate_limited` and `unreachable` are reported and the item is re-queued (after the pause, via the limiter). `error` is retried up to `max_error_retries` times, sleeping `backoff_s[0]` on the clock between tries, then is final. `ok`/`empty` are final.
- `on_outcome` is awaited for each final outcome as soon as it exists, before other batches finish.
- `GlobalFailure` (from `report` or raised by `provider.fetch`) cancels outstanding batches and propagates; outcomes already handed to `on_outcome` stay handed.
- A provider returning the wrong number of outcomes is a `ValueError` naming the provider.

## Steps
- [ ] Write the failing tests (`FakeClock`, both fake providers via a parametrised fixture where the scenario applies):
  - `test_batches_follow_max_batch`: 7 entities → 7 calls on the fake, 2 calls (5 + 2) on the bulk fake.
  - `test_params_never_share_a_batch`
  - `test_concurrency_never_exceeds_policy`: a fetch that records how many calls overlap (threads + an event) never exceeds `concurrency`.
  - `test_pacing_spaces_starts`: with per_second=1, burst=1, 3 calls start ≥ 1 s apart on the fake clock.
  - `test_rate_limit_pauses_whole_provider_then_succeeds`: one rate_limited outcome → one pause of 30 s (+ jitter with a seeded rng) recorded in `clock.sleeps`; every item ends ok.
  - `test_global_failure_after_consecutive_episodes`: always rate_limited → `GlobalFailure` after `max_rate_limit_episodes` + 1 episodes; the pause schedule 30/60/120 is visible in `clock.sleeps`.
  - `test_unreachable_threshold_raises_global_failure`
  - `test_ok_resets_counters`
  - `test_error_retried_then_final`: scripted ["error", "error", "error"] → final error after 2 retries; ["error", "ok"] → ok.
  - `test_outcomes_delivered_before_abort`: items A, B ok then C triggers GlobalFailure → `on_outcome` saw A and B.
  - `test_wrong_outcome_count_raises`
- [ ] Run `uv run pytest packages/lensgraph/tests/test_source_scheduler.py -q`. Expected: FAIL.
- [ ] Implement. Don't modify `executor/limits.py` (that limiter is for node resources).
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): provider scheduler and shared rate limiter`.

Out of scope: deciding what to fetch (M4.2), persistence (M4.5).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 run_items batches by declared max_batch and never mixes params in a batch
- [ ] #2 ProviderLimiter enforces concurrency and token-bucket pacing, pauses the whole provider on a rate limit with the declared backoff and jitter
- [ ] #3 GlobalFailure after the declared consecutive rate-limit episodes or unreachable outcomes; ok resets the counters; errors retried then final
- [ ] #4 Every final outcome reaches on_outcome before an abort; tests pass against both fake providers
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
