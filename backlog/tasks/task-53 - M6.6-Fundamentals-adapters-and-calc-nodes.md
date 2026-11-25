---
id: TASK-53
title: M6.6 Fundamentals adapters and calc nodes
status: In Progress
assignee: []
created_date: '2026-11-25T08:17:59Z'
updated_date: '2026-11-25T23:25:44Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-49
  - TASK-50
references:
  - documentation/design/finance.md
type: feature
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Fundamentals frame adapters (`alpha_nodes.statements`) and the calc nodes behind the AI lenses: the `annual_fundamentals` transform plus profitability, balance sheet, cash generation and fundamental trend. Middle and top calculation layers; all maths lives in M6.2's kernels. After M6.1 (contracts) and M6.2 (kernels); runs alongside M6.4 and M6.5 (tests use hand-built canonical frames, not provider output). Spec: `documentation/design/finance.md` (Calculation layers; "Fundamentals: ... pinned conventions").

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/statements.py`: adapters
  - `packages/alpha_nodes/src/alpha_nodes/nodes/fundamental_calcs.py`: calc nodes
- Test: `packages/alpha_nodes/tests/test_statements.py`, `packages/alpha_nodes/tests/test_fundamental_calcs.py`
- Modify `documentation/design/finance.md` only if behaviour differs from it.

## Interfaces
Consumes: the M6.2 kernels; `FundamentalsSchema`, `PeriodWindow`, `ProfitabilityResult`, `BalanceSheetResult`, `CashGenerationResult`, `FundamentalTrendResult`, `require_same_currency`, `reference_day`, `FILING_LAG_DAYS`, `MAX_ANNUAL_PERIODS`, `Fundamentals` fetch node frame (canonical + fact meta columns) (M6.1); `CalcNode`, `TransformNode`, `NodeContext`, `Node.code_deps`.

Produces:
```python
# statements.py
class AnnualFundamentalsSchema(pa.DataFrameModel):   # FundamentalsSchema's columns + suspect: bool; unique ascending period_end
def known_on(frame: pd.DataFrame, day: date) -> pd.DataFrame
    # rows known on `day`: filed_at <= day, or filed_at null and period_end + FILING_LAG_DAYS <= day
def annual_periods(frame: pd.DataFrame, day: date, max_periods: int = MAX_ANNUAL_PERIODS) -> pd.DataFrame
    # annual rows known on `day`; per period_end the latest filed_at (null = oldest); last max_periods, ascending;
    # suspect = quality == "suspect"; CurrencyMismatch when periods differ in currency; empty input -> empty frame with the schema's columns
def period_window(annual: pd.DataFrame) -> PeriodWindow
def values(annual: pd.DataFrame, *columns: str) -> tuple[pd.DataFrame, PeriodWindow]
    # the rows where every named column is non-null (the periods a metric can use) and their window

# nodes/fundamental_calcs.py   (memoize=False and code_deps, like the price calc nodes)
class AnnualFundamentals(TransformNode): name = "annual_fundamentals"; inputs = {"fundamentals": "fundamentals"}
    output = AnnualFundamentalsSchema; max_periods: int = MAX_ANNUAL_PERIODS     # day = reference_day(ctx)
class Profitability(CalcNode):     name = "profitability";     inputs = {"annual": "annual_fundamentals"}; output = ProfitabilityResult
class BalanceSheet(CalcNode):      name = "balance_sheet";     inputs = {"annual": "annual_fundamentals"}; output = BalanceSheetResult
class CashGeneration(CalcNode):    name = "cash_generation";   inputs = {"annual": "annual_fundamentals"}; output = CashGenerationResult
class FundamentalTrend(CalcNode):  name = "fundamental_trend"; inputs = {"annual": "annual_fundamentals"}; output = FundamentalTrendResult
```
Each result's window describes the periods its fields used (for multi-field results: the periods of the field with the widest use; document which in the docstring). A missing line item gives None fields, never a failure; an empty frame gives `periods=0` results.

## Steps
- [ ] Write the failing tests (canonical frames built by a fixture helper in the test module, values chosen for hand computation):
  - `test_statements.py`: `test_known_on_uses_filed_at`, `test_known_on_applies_filing_lag_without_filed_at`, `test_annual_periods_takes_latest_filing_known_then` (a restatement filed after `day` is not used; before it, it wins), `test_annual_periods_caps_and_sorts`, `test_currency_change_raises`, `test_suspect_from_quality`, `test_empty_frame_keeps_columns`, `test_values_drops_periods_missing_a_column`.
  - `test_fundamental_calcs.py`: `test_profitability_hand_values` (ROE mean/min/std, margin mean/std, loss_years, cv), `test_roe_none_for_nonpositive_equity_period`, `test_balance_sheet_hand_values` and `test_interest_cover_none_without_interest`, `test_cash_generation_hand_values` (owner earnings with capex below and above D&A; FCF conversion; share-count CAGR over the period_end span), `test_fundamental_trend_hand_values` (1y growth, 3y CAGR with 4 periods, margin change, EPS growth via net_income / shares_diluted, FCF growth from a negative base), `test_trend_none_with_one_period`, `test_bank_without_operating_items_gives_none_margins`, `test_empty_fundamentals_give_zero_period_results`, `test_calc_nodes_declare_their_kernels`, `test_fundamental_calc_nodes_are_not_memoized`.
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_statements.py packages/alpha_nodes/tests/test_fundamental_calcs.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): fundamentals adapters and calc nodes (annual periods, profitability, balance sheet, cash generation, trend)`.

Out of scope: valuation and market cap (M6.7); registering nodes (M6.10); quarterly periods.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 alpha_nodes.statements adapters and the five nodes exist with exact names, inputs and outputs; no maths outside kernels
- [ ] #2 annual_periods applies the known-on rule (filed_at or 90-day lag) and keeps the latest filing known on the day
- [ ] #3 Hand-value tests pass for profitability, balance sheet, cash generation and trend; missing items give None, empty input gives periods=0
- [ ] #4 Calc nodes declare code_deps and are not memoized
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
Worker: dispatch ctx_dc517ccb0bcf, worktree task-53 (Orca run run_09eee9a7786f)
<!-- SECTION:NOTES:END -->
