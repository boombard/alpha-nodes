---
id: TASK-69
title: Finance fields declare units
status: To Do
assignee: []
created_date: '2026-11-26T04:35:00Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-67
  - TASK-54
  - TASK-62
references:
  - documentation/design/finance.md
  - documentation/design/core.md
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Finance declares units (core.md "Units"; finance.md "Units and currency are data"). Every numeric field of the price and fundamentals result models, and every numeric column of the canonical datasets and the annual-fundamentals frame, declares a unit. Money is prefixed from the right currency field. The dataset `metadata={"kind": ...}` tags are replaced by units. The glossary prompt notes stop restating units.

## Files
- Modify: `packages/alpha_nodes/src/alpha_nodes/units.py` (finance units: `MONEY` with `prefix_field="currency"`, `MONEY_PER_SHARE`, `SHARES`, and a trading-currency variant if a result has a trading-currency field; `FieldKind` removed), `datasets.py` (numeric columns `metadata={"unit": ...}`; non-numeric columns lose `kind`), `statements.py` (`AnnualFundamentalsSchema` columns), `metrics.py` (every numeric field, incl. Valuation and CapitalReturns), `lenses/price_behaviour.py` (claim templates use `{signed}` / `{value}`)
- Modify: glossary entries in `packages/alpha_nodes/src/alpha_nodes/glossary/` (drop unit restatements such as "0.15 means 15%"; keep the meaning of signs and multiples), `documentation/design/finance.md` (only if wording differs)
- Remove: the `require_units = False  # TASK-69` lines TASK-67 left on the finance lenses
- Test: `packages/alpha_nodes/tests/test_units.py` (new or extended), `test_datasets.py`, `test_metrics.py`, `test_glossary_finance.py`, `test_price_behaviour*.py`

## Steps
- [ ] Failing tests: `test_every_numeric_result_field_has_a_unit` (all metrics models), `test_every_numeric_dataset_column_has_a_unit`, `test_money_fields_prefix_an_existing_currency_field`, `test_ai_lens_plans_build_with_units`, `test_price_behaviour_claim_text` (e.g. "12-1 month total return +15.3%"), `test_prompt_notes_restate_no_units` (no `\d+(\.\d+)? means \d+%`).
- [ ] Run. Expected: FAIL.
- [ ] Implement. Wherever a money field's currency isn't the window's `currency` (trading vs reporting), ask; don't guess.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS. Render one quality_value user message from a fixture and paste a short excerpt into the summary.
- [ ] Commit: `feat(alpha_nodes): finance fields declare units`.

Expected side effect: the evidence of every finance lens changes, so their verdicts miss the cache once.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every numeric result field and canonical/annual frame column has a unit; dataset kind tags replaced
- [ ] #2 Money fields prefix an existing currency field (trading vs reporting resolved, not guessed)
- [ ] #3 price_behaviour claims and AI evidence show formatted values
- [ ] #4 Glossary prompt notes no longer restate units
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
