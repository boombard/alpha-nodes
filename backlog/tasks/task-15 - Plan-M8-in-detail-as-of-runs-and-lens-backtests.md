---
id: TASK-15
title: 'Plan M8 in detail: as-of runs and lens backtests'
status: To Do
assignee: []
created_date: '2026-11-23T08:03:33Z'
labels:
  - plan
  - sketch
milestone: m-7
dependencies:
  - TASK-14
references:
  - documentation/design/finance.md
type: task
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Also detail TASK-16 (aggregation v2: overlap discount, veto caps, subjective logic, calibration) and TASK-17 (AI lens repeated sampling) as part of M8, using the campaign and backtest data this milestone provides.

**From the scoring research (2026-11-23):** evaluate lenses by rank IC on `stance_mean` as well as by stance bucket. Before trusting an AI lens, measure its test-retest repeatability: run identical inputs several times and report agreement (e.g. ICC or share of identical stances). LLM-judge studies find run-to-run noise comparable to the signal.

**Does the reviewer earn its place? (noted 2026-11-24):** compare forward returns of review-vetoed and referred candidates against accepted ones (their dossiers are kept). If vetoes don't predict anything, drop or narrow the reviewer.

Sketched tasks:
- M8.1 as-of mode end to end: `RunConfig.as_of`, store queries filtered by known_at, AI nodes disabled by default / `backtest_valid=false`, `pit_reliable` and `level_based` warnings or refusal.
- M8.2 evaluation module: monthly as-of schedule, forward returns (1m/3m/12m vs benchmark) computed outside the graph, rank IC, stance-bucket returns, hit rate. [after M8.1 contracts]
- M8.3 backtest HTML report + 5-year demo on a fixed universe.

Design refs: finance.md (Lens backtests, Prices and point-in-time), overview.md (non-goals: AI backtesting).

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
