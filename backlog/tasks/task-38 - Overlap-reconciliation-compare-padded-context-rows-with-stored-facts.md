---
id: TASK-38
title: 'Overlap reconciliation: compare padded context rows with stored facts'
status: To Do
assignee: []
created_date: '2026-11-25T04:06:45Z'
labels:
  - core
  - sketch
dependencies:
  - TASK-30
references:
  - documentation/design/core.md
type: feature
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch, parked (user, 2026-11-25: note it, don't schedule yet). From the defensive review of the yfinance downloads.

**Problem.** Every check runs inside one provider response; nothing compares a response with the facts already stored. Two failures slip through:
- A lasting level shift. If Yahoo switches a series between pence and pounds and stays switched, only the first bar is flagged (`jump_x100`); later bars look normal next to it. If Yahoo restates the whole series in the new unit while the metadata still says GBp, nothing is flagged, and new facts sit 100x away from the stored ones.
- Late-posted splits. `restated_before` fires only for a split row inside the requested interval. If Yahoo posts the split row a day or more after the ex-date, stored closes before it stay unadjusted, a 2x/4x/10x discontinuity the 50x jump check misses.
- More generally, any retroactive Yahoo correction of stored history is never noticed.

**Idea.** Fetches are already padded back ~183 days for repair context, so most of each response overlaps facts the store holds: free evidence. Compare the overlap with the latest stored versions:
- a constant ratio ≠ 1 (a split ratio) → treat as a restatement: `restated_before` = the first differing date;
- a ratio near 100 → a unit problem: fail the fetch or mark the rows suspect;
- small noise → ignore (no versions from float noise).

**Shape.** Generic in lensgraph: normalise returns context rows marked as such (instead of trimming them), and the store compares them with its latest versions before dropping them, using a per-dataset comparison spec (which value columns, tolerance). Needs a core.md change and a decision on whether the provider or the store owns the rule. Would replace the fragile "split inside the requested interval" rule in the yfinance provider.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
