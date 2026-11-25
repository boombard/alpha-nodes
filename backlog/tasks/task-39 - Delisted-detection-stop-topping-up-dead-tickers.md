---
id: TASK-39
title: 'Delisted detection: stop topping up dead tickers'
status: To Do
assignee: []
created_date: '2026-11-25T05:17:05Z'
labels:
  - finance
  - sketch
dependencies:
  - TASK-37
references:
  - documentation/design/finance.md
  - documentation/design/core.md
type: feature
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch, parked (user, 2026-11-25: note it, plan it with M7 universe construction, TASK-14). From the TASK-37 review, ruling 1.

**Problem.** After TASK-37, a symbol whose timezone is known and that Yahoo answers with "no bars" over a range with sessions is `error`: it is retried and never cached, so a delisted or long-suspended ticker errors on every top-up (accepted cost in TASK-37: "delisting is M7/M8 work"). With `YF_POLICY.max_consecutive_errors=5`, five such tickers finishing in a row trip `GlobalFailure` and abort the fetch. Scattered dead names rarely do that, but a universe that is mostly dead (an old index membership in M8 as-of backtests) would trip it routinely. The breaker must keep counting "no bars", because a Yahoo incident looks exactly like that across the board.

**Idea.** Recognise delisting in the store instead of loosening the breaker: a symbol whose last stored bar is more than N sessions old, and that answered "no bars" on k separate runs, is marked delisted, with the date of its last bar. Top-ups past that date are skipped (no fetch, no error attempt); as-of reads before the delisting date still return its stored history. A later ok answer (relisting, a Yahoo hiccup that lasted k runs) clears the mark.

**Shape (open).** Where the mark lives: a generic "entity retired after <date>" state in lensgraph coverage (planning skips gaps after it), with the finance side deciding when to set it (sessions, N, k), or a finance-only universe concern in M7. Needs a design note in core.md or finance.md, a decision on N and k from the attempt log, and a way to list and clear marks (sources status CLI).

**Related case (TASK-48 live demo, 2026-11-25).** An *unknown* symbol takes a different path. ROG.SW (Roche, now RO.SW) gets a 404 "Quote not found" from Yahoo, yet `prices` is `ok` with 0 rows (`sources status` shows it as not covered), the calc nodes run on the empty frame, and `price_behaviour` abstains with "no components available". So a dead or renamed ticker is easy to miss in the report: nothing says "no price data". When this is planned, decide whether unknown symbols should be recognised alongside delisted ones (a mark, or a non-ok `prices` result) and whether the lens should give a clearer abstain reason when its price input is empty.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
