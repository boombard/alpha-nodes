---
id: TASK-14
title: 'Plan M7 in detail: campaigns and universe construction'
status: To Do
assignee: []
created_date: '2026-11-23T08:03:32Z'
labels:
  - plan
  - sketch
milestone: m-6
dependencies:
  - TASK-13
references:
  - documentation/design/core.md
  - documentation/design/finance.md
type: task
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketched tasks:
- M7.1 contracts (lensgraph): `CampaignSpec`, `Quotas`, `Stage`, `Budget`, `Population` protocol, stratum key and policy registries, campaign record models.
- M7.2 allocation (deficit / Beta-prior pass rate, budget caps, seeded draws) as pure, property-tested logic. [parallel]
- M7.3 campaign loop over staged partial runs + shortfall report + persistence of draws/decisions. [parallel]
- M7.4 `yfinance_screen` population (full paginated screen, USD thresholds via fx, sector from profile) + finance universe campaign + report section.

Design refs: core.md (Campaigns), finance.md (Universe campaign).

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
