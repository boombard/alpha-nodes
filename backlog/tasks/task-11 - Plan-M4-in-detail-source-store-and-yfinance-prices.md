---
id: TASK-11
title: 'Plan M4 in detail: source store and yfinance prices'
status: To Do
assignee: []
created_date: '2026-11-23T08:03:31Z'
updated_date: '2026-11-23T23:51:20Z'
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
- M4.6 e2e: two runs over 10 mixed tickers, network only on the first; suspect rows surface.

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
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
