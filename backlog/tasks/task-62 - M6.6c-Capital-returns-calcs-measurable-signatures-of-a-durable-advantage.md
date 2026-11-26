---
id: TASK-62
title: 'M6.6c Capital-returns calcs: measurable signatures of a durable advantage'
status: To Do
assignee: []
created_date: '2026-11-26T00:19:44Z'
updated_date: '2026-11-26T00:28:29Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-53
  - TASK-55
  - TASK-61
  - TASK-64
references:
  - documentation/design/finance.md
type: feature
ordinal: 62000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A moat cannot be computed, but it leaves measurable signatures: high returns on capital that persist instead of mean-reverting, new capital that keeps earning high returns, margins that hold up in bad years, and a low reinvestment need. ROE (the only returns measure today) is inflated by leverage and buybacks and breaks with negative equity. This task adds a `capital_returns` calc node whose citable fields give the `quality_value` lens that evidence; the lens still judges the advantage, it never gets a "moat score". Pre-tax, because tax expense is not ingested. Fields are None where they do not apply (banks and insurers have no operating income; invested capital ≤ 0). Spec: `documentation/design/finance.md` (2. quality_value calc inputs; Fundamentals pinned conventions; Calculation layers), `core.md` (AI nodes).

## Files
- Modify:
  - `packages/alpha_nodes/src/alpha_nodes/kernels/fundamentals.py`: `invested_capital`, `incremental_return`
  - `packages/alpha_nodes/src/alpha_nodes/metrics.py`: `CapitalReturnsResult`
  - `packages/alpha_nodes/src/alpha_nodes/nodes/fundamental_calcs.py`: `CapitalReturns`
  - `packages/alpha_nodes/src/alpha_nodes/lenses/quality_value.py`: `capital_returns` input
  - `packages/alpha_nodes/src/alpha_nodes/prompts/quality_value.md.j2`, `prompts/quality_value_buffett_persona.md.j2`: point the durable-advantage principle at `capital_returns`
  - `documentation/design/finance.md`: quality_value calc inputs; a pinned-conventions bullet for the new fields
- Create: glossary entries for the new fields in `packages/alpha_nodes/src/alpha_nodes/glossary/` (e.g. `roic-pretax.md`, `incremental-roic.md`, `op-margin-floor.md`, `capex-intensity.md`), `status: draft`, in the TASK-64 format (prompt notes state basis, window, units and the base-period fallback); no lens edit is needed for them: `quality_value`'s data dictionary is derived from its inputs, and a plan with an unclaimed `CapitalReturnsResult` field fails
- Test: `packages/alpha_nodes/tests/test_kernels_fundamentals.py`, `test_metrics.py`, `test_fundamental_calcs.py`, `test_quality_value_lens.py`

## Interfaces
Consumes: `safe_ratio`, `mean_std` (M6.2); `FINANCE_GLOSSARY_DIR` and the entry format (TASK-63/64/66); `values`, `period_window`, `years_between` (TASK-53); `PeriodWindow.field_periods` (TASK-61); `QualityValue` (TASK-55).

Produces:
```python
# kernels/fundamentals.py   (nan in, ValueError; cannot compute -> nan, as the other kernels)
def invested_capital(total_debt: np.ndarray, total_equity: np.ndarray, cash: np.ndarray) -> np.ndarray
    # debt + equity - cash per period
def incremental_return(op_income_start: float, op_income_end: float,
                       capital_start: float, capital_end: float) -> float
    # (op_end - op_start) / (cap_end - cap_start); nan when the capital change <= 0

# metrics.py
class CapitalReturnsResult(PeriodWindow):
    roic_pretax_mean: float | None     # operating_income / invested capital, per period (None when IC <= 0)
    roic_pretax_min: float | None
    roic_pretax_std: float | None      # ddof=1, needs >= 3 periods
    incremental_roic_pretax: float | None   # over the base ~3-5y back (closest period to 5y, within 6 months;
                                            # else ~3y), None when invested capital did not grow
    op_margin_min: float | None        # worst operating margin in the window (pricing power in bad years)
    capex_to_revenue_mean: float | None
    capex_to_da_mean: float | None     # > 1 means growth capex beyond maintenance

# nodes/fundamental_calcs.py   (memoize=False, code_deps)
class CapitalReturns(CalcNode): name = "capital_returns"; inputs = {"annual": "annual_fundamentals"}
    output = CapitalReturnsResult
    # window: the widest field's periods (documented, as Profitability)

# lenses/quality_value.py
inputs gains "capital_returns": "capital_returns"
```
Prompt (both variants): the durable-advantage principle says "look for returns on capital that stay high and stable (`capital_returns`), new capital earning high returns, margins that hold up in bad years and a low reinvestment need; these are signs, not proof; judge the advantage itself from the business description".

## Steps
- [ ] Write the failing tests:
  - kernels: `test_invested_capital`, `test_incremental_return_hand_value`, `test_incremental_return_nan_when_capital_shrinks`, `test_kernels_reject_non_finite`.
  - metrics: `test_capital_returns_result_fields`.
  - calcs: `test_capital_returns_hand_values` (ROIC mean/min/std, incremental ROIC over 5y, margin floor, capex ratios), `test_roic_none_when_invested_capital_nonpositive`, `test_bank_without_operating_income_gives_none`, `test_incremental_falls_back_to_3y_base`, `test_capital_returns_empty_gives_zero_periods`, `test_capital_returns_declares_kernels_and_not_memoized`.
  - lens: `test_capital_returns_is_an_input_and_citable`, `test_prompt_points_advantage_at_capital_returns` (both variants).
- [ ] Run the four test modules. Expected: FAIL.
- [ ] Implement; update finance.md.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): capital-returns calcs for the quality_value lens`.

Out of scope: gross margin (gross profit not ingested); after-tax ROIC (tax expense not ingested); goodwill adjustments; a numeric moat score; registering the node (TASK-57).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 invested_capital and incremental_return kernels with tests; no maths in the node beyond kernel calls
- [ ] #2 CapitalReturns gives pre-tax ROIC level/min/std, incremental ROIC, margin floor and capex ratios, None where not applicable (no operating income, invested capital <= 0)
- [ ] #3 quality_value takes capital_returns as an input and both prompts point the durable-advantage principle at it, as signs not proof
- [ ] #4 finance.md lists the new calc inputs and their conventions
- [ ] #5 The new fields have glossary entries (draft); the finance glossary coverage tests and the quality_value plan-build test pass
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
