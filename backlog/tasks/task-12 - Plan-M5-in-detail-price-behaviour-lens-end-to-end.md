---
id: TASK-12
title: 'Plan M5 in detail: price-behaviour lens end-to-end'
status: To Do
assignee: []
created_date: '2026-11-23T08:03:32Z'
updated_date: '2026-11-25T06:03:36Z'
labels:
  - plan
  - sketch
milestone: m-4
dependencies:
  - TASK-34
  - TASK-42
references:
  - documentation/design/finance.md
type: task
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketched tasks:
- M5.1 calc nodes: momentum 12-1, trend vs 200d MA + slope, realised vol (1y annualised), max drawdown (3y); ratio-based (as-of safe); exact-value tests on synthetic series, plus TA-Lib oracle tests where an equivalent exists (SMA, LINEARREG_SLOPE, STDDEV; see finance.md, Technical analysis and TA-Lib). Return/vol conventions pinned in finance.md. [parallel; needs TASK-42 for the ta-lib dev dependency]
- M5.2 `price_behaviour` DeterministicLens with components and default thresholds as params. [after M5.1 contracts]
- M5.3 finance report renderers (price chart, metrics table). [parallel]
- M5.4 100-ticker demo run YAML + e2e (recorded fixtures in tests; live run is the demo gate).

Design refs: finance.md (v1 lenses: price_behaviour).

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
