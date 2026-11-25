---
id: TASK-11
title: 'Plan M4 in detail: source store and yfinance prices'
status: Done
assignee: []
created_date: '2026-11-23T08:03:31Z'
updated_date: '2026-11-25T02:27:01Z'
labels:
  - plan
  - sketch
milestone: m-3
dependencies:
  - TASK-22
references:
  - documentation/design/core.md
  - documentation/design/finance.md
type: task
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketched tasks:
- M4.1 contracts (lensgraph): `Dataset`, `Provider` protocol with outcome classification (ok/empty/error/GlobalFailure), `SourceStore` protocol, fact row schema (`provider`, `fetch_id`, `first_seen_at`, `known_at`, `normaliser_version`, `repairs`, `quality`), interval-set type. [sequential]
- M4.2 interval coverage + fetch-attempt log + per-dataset TTL (pure logic, heavily unit-tested: mid-range holes, union not overwrite, freshness per interval, empty-outcome TTL). [parallel]
- M4.3 DuckDB source store: raw responses layer, append-only canonical facts, as-of query, `renormalise`, offline mode. [parallel]
- M4.4 `alpha_nodes` package scaffold + canonical `prices`, `profile`, `fx` schemas (units/kinds, two currencies) + `DatasetFetch` node. [after M4.1]
- M4.5 `YFinanceProvider` for prices/profile/fx: pinned yfinance, `repair=True`, GBp/GBX->GBP repair, 100x-jump and calendar checks, error classification; recorded-fixture contract tests for the canary tickers; separate `scripts/canary.py` (not in tests).
- M4.6 e2e: two runs over 10 UK/European tickers (+1 US), network only on the first; suspect rows surface.

**Inputs from 2026-11-25 (see core.md Source store, finance.md "yfinance fetching and throttling", D24/D25):** UK + Europe focus (per-exchange calendars, multi-currency, dual listings in profile). M4.1 adds provider capability declaration (max_batch, rate-limit policy, settled cut-off). Core owns scheduling + a shared per-provider limiter (pause on rate limit, GlobalFailure thresholds, persist per work item). Tests use two fake providers with different capabilities to prove the core assumes nothing yfinance-specific.

Design refs: core.md (Source store), finance.md (Datasets, Providers, Data quality, Prices and point-in-time, Currency), lessons.md (caching lessons).

## How to do this task (coordinator/Opus, not a worker)
1. Re-read the milestone file, the design sections listed, and the code as it now stands.
2. Create this milestone's tasks with `backlog task create` in the format of task-1 to task-9:
   - Description sections: Files, Interfaces (Consumes/Produces with exact signatures), Steps (TDD, with test names and assertions), Out of scope.
   - Single-line ACs, `--dep` edges, the milestone, and labels.
   - The first task is a `contracts` task when the milestone introduces new shared interfaces.
   - Tasks that run concurrently touch disjoint files.
3. Re-point the next "Plan M…" task's dependency at this milestone's final task.
4. Get the human's approval of the new tasks before starting any of them.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run pytest` passes (whole workspace)
- [x] #2 `uv run ruff check` and `uv run pyright` are clean
- [x] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [x] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Planned M4 as TASK-26 (contracts) -> {TASK-27 coverage planning, TASK-28 scheduler + limiter, TASK-29 alpha_nodes datasets/markets} -> {TASK-30 DuckDB source store, TASK-31 yfinance prices+fx} -> {TASK-32 yfinance profile + canary, TASK-33 DatasetFetch + sources run config + CLI} -> TASK-34 finance e2e (M4 demo gate). Throttle defaults confirmed (concurrency 4, ~2 req/s burst 4, provider-wide pause 30/60/120/240 s, GlobalFailure after 3 rate-limit episodes or 5 unreachable). Planning decisions approved by the human 2026-11-25: no adjusted close stored (computed in M5), no market cap in profile, settled history never expires (TTL covers the unsettled tail, snapshots and empty outcomes), providers report restated_before (e.g. new splits), sources: section in run config with a domain SourceCatalog, batching only within one ensure call. Docs are updated by the implementing tasks. TASK-12 re-pointed to TASK-34.
<!-- SECTION:FINAL_SUMMARY:END -->
