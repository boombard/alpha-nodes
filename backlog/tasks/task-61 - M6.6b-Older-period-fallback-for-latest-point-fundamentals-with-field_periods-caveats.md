---
id: TASK-61
title: >-
  M6.6b Older-period fallback for latest-point fundamentals, with field_periods
  caveats
status: In Review
assignee: []
created_date: '2026-11-26T00:02:56Z'
updated_date: '2026-11-26T01:18:55Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-53
  - TASK-55
references:
  - documentation/design/finance.md
type: feature
ordinal: 61000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Latest-point fundamentals fields (leverage, coverage, net debt, owner earnings, FCF) currently come only from the newest annual period and are None when that row lacks an item, which drops evidence the AI lenses could weigh (common for yfinance's newest year). This task lets each such field fall back to the newest period, at most `MAX_STALE_PERIODS` (2) periods back, in which all of its inputs are present, and records the period it came from in a `field_periods` map on the result, so the lens sees the caveat as data and adjusts its conviction. A ratio never mixes periods: numerator and denominator come from the same row. Past the cap the field stays None. After M6.6 (TASK-53) and M6.8 (TASK-55). Spec: `documentation/design/finance.md` ("Fundamentals: ... pinned conventions"; "Lens inputs and abstention", extended by this task); `documentation/design/core.md` (AI nodes: the lens interprets, never computes).

## Files
- Modify:
  - `packages/alpha_nodes/src/alpha_nodes/metrics.py`: `PeriodWindow.field_periods`
  - `packages/alpha_nodes/src/alpha_nodes/conventions.py`: `MAX_STALE_PERIODS`
  - `packages/alpha_nodes/src/alpha_nodes/statements.py`: `latest_complete`
  - `packages/alpha_nodes/src/alpha_nodes/nodes/fundamental_calcs.py`: `BalanceSheet`, `CashGeneration`
  - `packages/alpha_nodes/src/alpha_nodes/prompts/quality_value.md.j2` and `prompts/quality_value_buffett_persona.md.j2`: one instruction line each
  - `documentation/design/finance.md`: the Leverage, Owner earnings and FCF bullets of the pinned conventions, and "Lens inputs and abstention"
- Test: `packages/alpha_nodes/tests/test_statements.py`, `packages/alpha_nodes/tests/test_fundamental_calcs.py`, `packages/alpha_nodes/tests/test_quality_value_lens.py`, and the existing metrics model test module

## Interfaces
Consumes: `annual_periods`, `values`, `period_window` and the M6.6 calc nodes (TASK-53); `QualityValue` and its prompts (TASK-55); `PeriodWindow` and the result models (TASK-49).

Produces:
```python
# conventions.py
MAX_STALE_PERIODS = 2   # a latest-point field may come from at most 2 periods before the latest

# metrics.py, on PeriodWindow (so every fundamentals result, incl. TASK-54's ValuationResult, can use it)
field_periods: dict[str, date] = {}   # field name -> period_end it came from, ONLY for fields older than
                                      # last_period_end; empty when every field is from the latest period
    # validator: every key is a field of the model; every date < last_period_end

# statements.py
def latest_complete(annual: pd.DataFrame, *columns: str,
                    max_stale: int = MAX_STALE_PERIODS) -> pd.DataFrame
    # the newest single row among the last max_stale + 1 periods where every named column is non-null;
    # empty when none qualifies
```
Node behaviour:
- `BalanceSheet`: `debt_to_equity` (total_debt, common_equity), `interest_cover` (operating_income, interest_expense) and `net_debt` (total_debt, cash) each from their own `latest_complete` row. The window spans from the oldest row used to the latest period (as FundamentalTrend); the docstring says so.
- `CashGeneration`: `owner_earnings` (net_income, depreciation_amortization, capex) and `fcf` (operating_cash_flow, capex) likewise; `fcf_conversion` and `share_count_cagr` unchanged (already windowed).
- A field computed from a non-latest row gets `field_periods[field] = that row's period_end`.
- Both quality_value prompts, one line in the instructions: "Fields listed in a result's `field_periods` come from an older period than its `last_period_end`; weigh them accordingly, lower your conviction when key fields are stale, and say so."

## Steps
- [ ] Write the failing tests:
  - metrics: `test_field_periods_default_empty`, `test_field_periods_rejects_unknown_field_and_non_older_date`.
  - `test_statements.py`: `test_latest_complete_takes_newest_row_with_all_columns`, `test_latest_complete_respects_max_stale`, `test_latest_complete_empty_frame`.
  - `test_fundamental_calcs.py`: `test_balance_sheet_falls_back_to_older_period_and_records_it` (latest lacks interest_expense: interest_cover from the year before and listed in field_periods; debt_to_equity from the latest and not listed), `test_ratio_inputs_from_one_period` (total_debt only in latest, common_equity only in latest-1: debt_to_equity from the newest row with both, never mixed), `test_fallback_beyond_max_stale_is_none`, `test_cash_generation_owner_earnings_fallback`, `test_window_spans_oldest_used_row`.
  - `test_quality_value_lens.py`: `test_prompt_mentions_field_periods` (both variants), `test_field_periods_rendered_in_context`.
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_statements.py packages/alpha_nodes/tests/test_fundamental_calcs.py packages/alpha_nodes/tests/test_quality_value_lens.py -q`. Expected: FAIL.
- [ ] Implement; update finance.md (pinned conventions: "latest" means the newest period within MAX_STALE_PERIODS with all of a field's inputs, recorded in field_periods; Lens inputs: the lenses see field_periods and weigh staleness).
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): older-period fallback for latest-point fundamentals with field_periods`.

Out of scope: valuation fields (TASK-54 adopts `latest_complete` and `field_periods`); the price_vs_fundamentals prompt (TASK-56 includes the same instruction line); deterministic down-weighting of stale fields (the lens judges); quarterly periods.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 PeriodWindow.field_periods exists (default empty, validated); MAX_STALE_PERIODS = 2 in conventions
- [ ] #2 BalanceSheet and CashGeneration latest-point fields fall back at most 2 periods to the newest row with all their inputs, never mixing periods within a field, and record older periods in field_periods
- [ ] #3 Both quality_value prompts tell the lens to weigh fields in field_periods and lower conviction when key fields are stale
- [ ] #4 finance.md documents the fallback, the cap and field_periods
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
Worker: dispatch ctx_104e86b57bc6, worktree task-61
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: latest_complete + MAX_STALE_PERIODS=2; BalanceSheet/CashGeneration fields each fall back to the newest complete row of the last 3 periods (one row per field, no period mixing, None past cap); PeriodWindow.field_periods records older fields, validated (known field names, dates < last_period_end); one instruction line in both quality_value prompts; finance.md pinned conventions + Lens inputs updated. pytest 1105 passed, ruff/pyright clean. Review: 3 rounds. Round 1: finance.md edit missing from branch; CashGeneration crash when _widest's window ended before the frame's latest period (field_periods failed validation). Round 2 (human-approved): CashGeneration now reports a spanning window (_span: earliest start among conv/share/latest-point windows to the frame's latest period), so field_periods always flags fields older than the newest row; _widest unchanged for Profitability. All findings resolved. Verdict: approve. Rulings: BalanceSheet and CashGeneration windows span oldest used row to latest period (periods counts rows spanned, not rows with every input); window includes the latest row even when no field qualified; other nodes leave field_periods empty; tests that dump whole results exclude field_periods.
<!-- SECTION:FINAL_SUMMARY:END -->
