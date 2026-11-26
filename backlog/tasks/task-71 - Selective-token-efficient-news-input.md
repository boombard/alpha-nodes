---
id: TASK-71
title: Selective, token-efficient news input
status: To Do
assignee: []
created_date: '2026-11-26T09:25:45Z'
labels:
  - finance
  - sketch
dependencies:
  - TASK-70
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch, parked (TASK-70 took news out of `quality_value`). Bring news back only as a selective, token-efficient input.

Ideas to weigh when this is planned:
- **Select deterministically, before the model sees anything.** Keep material events only (results, guidance, M&A, capital actions, management change, litigation, regulation) by event type or keyword rules. Drop syndicated duplicates and price-move recaps ("shares rise 3%").
- **Fewer, shorter items.** Headline + source + date by default, at most about 3 items. The summary only for items that pass the materiality filter, cut to a fixed character budget.
- **A token budget per input.** The renderer stops adding evidence once an input's budget is used, and the input-depth note says so. A core mechanism, since other text inputs need it too.
- **Maybe a cheap classifier node.** It tags materiality, with the tags validated against a closed list. Its output is labels, never numbers used in scoring.
- **Measure first.** Compare verdicts with and without news on the M6 panel (`compare_variants.py`), to see whether news changes any stance at all before spending on it.

Open: is news a `quality_value` input or a lens of its own (an event or catalyst lens)? yfinance news can't be backtested (finance.md).
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
