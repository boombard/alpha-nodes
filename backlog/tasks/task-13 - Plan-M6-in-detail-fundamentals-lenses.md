---
id: TASK-13
title: 'Plan M6 in detail: fundamentals lenses'
status: To Do
assignee: []
created_date: '2026-11-23T08:03:32Z'
labels:
  - plan
  - sketch
milestone: m-5
dependencies:
  - TASK-12
references:
  - documentation/design/finance.md
type: task
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
**Note from the scoring research (2026-11-23):** LLMs drift toward analyst ratings placed in their context (reported herding; weak evidence, but cheap to guard). Don't feed analyst consensus or price targets into an AI lens's context unless that is the lens's deliberate purpose, and record the choice in the lens's docstring.

Sketched tasks:
- M6.1 contracts: canonical `fundamentals`, `filings_text`, `news` schemas with field kinds; money/currency calc helpers that refuse mixed currencies without fx.
- M6.2 `EdgarProvider` (companyfacts XBRL, ticker->CIK map, curated tag map, filing dates, 10-K sections; SEC User-Agent from settings). [parallel]
- M6.3 yfinance fundamentals/news adapters (statement merge on period_end, sparse-column drop, balance check, capex sign, no `.info` ratios). [parallel]
- M6.4 quality calc nodes (ROE level/consistency, margins, leverage, owner earnings, FCF conversion, share-count trend, valuation band). [after M6.1]
- M6.5 `quality_value` AINode: rubric prompt with sourced principles (default) + `buffett_persona` variant; depth `desired_periods=8, min_periods=3`.
- M6.6 `price_vs_fundamentals` AINode (divergence framing, flag codes) + mixed US/UK/AU demo run.

Design refs: finance.md (Datasets, Providers, Data quality, v1 lenses 2 and 3, Known data limitations).

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
