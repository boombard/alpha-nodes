---
id: TASK-69
title: Finance fields declare units
status: In Review
assignee: []
created_date: '2026-11-26T04:35:00Z'
updated_date: '2026-11-26T08:04:19Z'
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
- Modify (DRY follow-up from TASK-54 review): one public scalar-helper module for the nan-to-None and scalar-ratio glue (e.g. `packages/alpha_nodes/src/alpha_nodes/scalars.py`: `opt`, `ratio`), used by `nodes/price_calcs.py`, `nodes/fundamental_calcs.py`, `valuation.py` and `nodes/valuation_calcs.py` in place of their private `_opt` / `_ratio` copies (update their `code_deps`); test `packages/alpha_nodes/tests/test_scalars.py`
- Remove: the `require_units = False  # TASK-69` lines TASK-67 left on the finance lenses
- Test: `packages/alpha_nodes/tests/test_units.py` (new or extended), `test_datasets.py`, `test_metrics.py`, `test_glossary_finance.py`, `test_price_behaviour*.py`

## Steps
- [ ] Failing tests: `test_every_numeric_result_field_has_a_unit` (all metrics models), `test_every_numeric_dataset_column_has_a_unit`, `test_money_fields_prefix_an_existing_currency_field`, `test_ai_lens_plans_build_with_units`, `test_price_behaviour_claim_text` (e.g. "12-1 month total return +15.3%"), `test_prompt_notes_restate_no_units` (no `\d+(\.\d+)? means \d+%`).
- [ ] Run. Expected: FAIL.
- [ ] DRY: move `_opt` / `_ratio` into the shared scalar-helper module (tests first in `test_scalars.py`) and switch all four callers to it; no behaviour change.
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
- [ ] #5 One shared scalar-helper module replaces the private `_opt` / `_ratio` copies in price_calcs, fundamental_calcs, valuation and valuation_calcs
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From TASK-67 review (2026-11-26): (1) price_behaviour claim templates were switched to {raw:+.1%} as a stopgap. Once FRACTION / FRACTION_PER_YEAR are declared on those fields, convert them to {signed} (or {value}) so they use format_value. (2) Bare scalar outputs (output = float) are not unit-checked. Keep every finance numeric output a pydantic or pandera model so its fields carry units.

From TASK-68 (user ruling 2026-11-26): once finance fields declare units, click through unit-bearing cites in a real finance run report in a browser: field tables show display strings (e.g. 15.3%, USD 12.3bn), DataGrid headers carry unit ids, columns sort on raw values.

Worker: dispatch ctx_d93667c4110d, worktree task-69

User ruling 2026-11-26: PriceWindow gains a trading-currency `currency` field so TrendResult.close/ma are prefixed money (Files widened). Review round 1 sent (dispatch ctx_e2951e46125b) from head 001b877.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, worktree task-69, 4 commits 6d08646..7bd9248): every numeric result field, canonical dataset column and AnnualFundamentals column declares a unit; kind tags and FieldKind removed; finance units MONEY, MONEY_PER_SHARE (prefix currency), TRADING_MONEY_PER_SHARE (prefix trading_currency, ValuationResult.close), SHARES; price_behaviour claims use {signed}/{value}; glossary prompt notes stop restating units; require_units=False removed from price_behaviour, quality_value and price_vs_fundamentals; opt/ratio shared in alpha_nodes/scalars.py across the four callers. pytest 1259 passed, ruff and pyright clean. Evidence excerpt: trend = {bars: '300 bars', currency: 'GBP', close: 'GBP 189', ma: 'GBP 175', pct_above_ma: '7.9%', ma_slope: '8.1%/yr'}; balance_sheet = {debt_to_equity: '0.3×', interest_cover: '12×', net_debt: 'USD 5'}.

Review: 2 rounds. R1: user ruling added PriceWindow.currency (trading currency, carried via TotalReturnSchema.currency, filled in window_info) so TrendResult.close/ma are prefixed money (Files widened to series.py and its tests); restored the multiple meanings in interest-cover and debt-to-equity glossary notes. R2: finance.md money-units bullet wording. Verdict: approve.

Open points: (a) TASK-68 browser click-through of unit-bearing cites in a real finance run report not done (needs the human); (b) MONEY_PER_SHARE renders at 3 significant figures (189.20 -> 'GBP 189'); (c) op_margin_change_1y is FRACTION ('+2.0%') though it is a percentage-point change; (d) finance lens verdict caches miss once (expected).
<!-- SECTION:FINAL_SUMMARY:END -->
