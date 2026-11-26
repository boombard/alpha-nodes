---
id: TASK-64
title: 'Finance glossary: seed entries for every price and fundamentals field'
status: To Do
assignee: []
created_date: '2026-11-26T00:28:00Z'
updated_date: '2026-11-26T00:28:28Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-63
  - TASK-51
  - TASK-53
  - TASK-55
  - TASK-56
  - TASK-61
references:
  - documentation/design/finance.md
type: feature
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The finance glossary content (finance.md "Glossary", added by this task): one entry per term behind every citable
field of the price (Momentum, Trend, Volatility, Drawdown) and fundamentals (Profitability, BalanceSheet,
CashGeneration, FundamentalTrend, Valuation, ValuationChange) result models, all `status: draft` (written from model
knowledge; research upgrades them later). Window fields (bars, periods, dates, currency, suspect counts,
field_periods) share one entry each for "price window" and "period window". The per-term formulas in finance.md
move into the entries and the bullets link them. Both AI lenses declare their terms. Roughly 25-30 entries, each
with a `summary` and a `category` (price, profitability, leverage, cash generation, growth, valuation, window),
formulas in `$...$` math, and cross-references as relative `.md` links.

## Files
- Create: `packages/alpha_nodes/src/alpha_nodes/glossary/*.md` (entries) and `glossary/__init__.py`
  (`FINANCE_GLOSSARY = Glossary.load(<this dir>)`); package-data config in `packages/alpha_nodes/pyproject.toml`
  if needed so the .md files ship
- Modify: `lenses/quality_value.py`, `lenses/price_vs_fundamentals.py` (`glossary`, `glossary_terms`);
  `documentation/design/finance.md` (section B); `documentation/README.md` (link); `backlog/docs/doc-1` is the
  coordinator's (line C)
- Test: `packages/alpha_nodes/tests/test_glossary_finance.py`

## Steps
- [ ] Failing tests: `test_finance_glossary_loads`, `test_every_result_field_has_one_entry` (iterates the result
  models in alpha_nodes.metrics, excluding nothing: window fields map to the window entries),
  `test_implemented_by_resolves`, `test_lenses_declare_terms_for_all_their_input_fields` (for each AI lens, the
  terms of every field of its input result models are in glossary_terms), `test_prompt_notes_have_no_formulas`
  (no "=" or arithmetic operators in prompt notes).
- [ ] Run. Expected: FAIL.
- [ ] Write the entries; wire the lenses; edit finance.md (move formulas, link entries; keep policy text).
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`; `uv run lensgraph glossary
  packages/alpha_nodes/src/alpha_nodes/glossary` lists every entry as draft. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): finance glossary seeded for price and fundamentals fields`.

Out of scope: researching and verifying entries (later, per term); turning the glossary on for dev runs.

Design text for finance.md (write it in this task): the approved draft, copied below.

## B. finance.md: changes

- New short section "Glossary": the finance glossary lives in
  `packages/alpha_nodes/src/alpha_nodes/glossary/` (package data); every citable field of the
  price and fundamentals result models has exactly one entry (tested). Each lens declares the
  terms of its inputs.
- "Fundamentals: pinned conventions" and the price_behaviour metric definitions: per-term
  formulas move to their entries; the bullets keep the policy and link the entry
  (e.g. "**FCF**: see glossary `fcf`; capex sign pinned positive, see Providers").
- Calculation layers: a new calc field needs a glossary entry in the same task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every citable price and fundamentals result field has exactly one entry; all entries validate and their implemented_by paths resolve
- [ ] #2 quality_value and price_vs_fundamentals declare the terms of all their input fields
- [ ] #3 finance.md per-term formulas live in the entries; the conventions keep policy and link them
- [ ] #4 Prompt notes are interpretive and contain no formulas
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
