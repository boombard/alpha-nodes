---
id: TASK-50
title: M6.2 Fundamentals numpy kernels
status: In Review
assignee: []
created_date: '2026-11-25T08:17:39Z'
updated_date: '2026-11-25T08:28:45Z'
labels:
  - finance
milestone: m-5
dependencies: []
references:
  - documentation/design/finance.md
type: feature
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Pure numpy kernels for the fundamentals maths: ratios with non-positive denominators, growth, CAGR, mean/std, coefficient of variation, owner earnings, sum ratios and capitalised value. Bottom calculation layer; no dependencies, runs alongside M6.1 (contracts). Spec: `documentation/design/finance.md` (Calculation layers; "Fundamentals: ... pinned conventions").

## Files
- Create: `packages/alpha_nodes/src/alpha_nodes/kernels/fundamentals.py`
- Modify: `packages/alpha_nodes/src/alpha_nodes/kernels/__init__.py` (export the new kernels)
- Test: `packages/alpha_nodes/tests/test_kernels_fundamentals.py`

## Interfaces
Consumes: `alpha_nodes.kernels._validate` (the existing finite-input checks).

Produces (`alpha_nodes.kernels.fundamentals`; 1-D float64 arrays and plain floats; non-finite input raises `ValueError`; scalars return `nan` when they can't be computed; each docstring states its formula):
```python
def safe_ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray   # num/den elementwise; nan where den <= 0; ValueError on length mismatch
def growth(prev: float, cur: float) -> float                     # (cur - prev) / |prev|; nan when prev == 0
def cagr(first: float, last: float, years: float) -> float       # (last/first)**(1/years) - 1; nan unless first > 0, last > 0, years > 0
def mean_std(x: np.ndarray, min_n: int = 3) -> tuple[float, float]   # mean (nan if empty); std ddof=1 (nan if len < min_n)
def coefficient_of_variation(x: np.ndarray, min_n: int = 3) -> float # std/mean; nan when mean <= 0 or len < min_n
def owner_earnings(net_income: np.ndarray, dep_amort: np.ndarray, capex: np.ndarray) -> np.ndarray
    # net_income + dep_amort - minimum(capex, dep_amort)
def sum_ratio(num: np.ndarray, den: np.ndarray) -> float         # sum(num)/sum(den); nan when empty or sum(den) <= 0
def capitalised_value(earnings: float, rate: float) -> float     # earnings / rate; nan when earnings <= 0; ValueError when rate <= 0
```

## Steps
- [ ] Write the failing tests in `test_kernels_fundamentals.py`, hand-computed values on tiny arrays plus edges per kernel:
  - `test_safe_ratio_values_and_nonpositive_denominator`, `test_safe_ratio_length_mismatch_raises`
  - `test_growth_hand_value`, `test_growth_from_negative_base` ((-50) -> 25 gives 1.5), `test_growth_zero_base_is_nan`
  - `test_cagr_hand_value` (100 -> 121 over 2 years = 0.10), `test_cagr_nan_for_nonpositive_ends`
  - `test_mean_std_ddof_1`, `test_mean_std_short_gives_nan_std`, `test_mean_std_empty`
  - `test_cv_hand_value`, `test_cv_nan_when_mean_not_positive`
  - `test_owner_earnings_caps_maintenance_at_capex` (capex < D&A) and `test_owner_earnings_capex_above_da`
  - `test_sum_ratio_hand_value`, `test_sum_ratio_nan_when_denominator_sum_not_positive`
  - `test_capitalised_value_hand_value`, `test_capitalised_value_negative_earnings_nan`, `test_capitalised_value_rejects_nonpositive_rate`
  - `test_non_finite_input_raises` (parametrised over the array kernels)
  - No TA-Lib oracle: fundamentals have no TA-Lib equivalent (finance.md, Technical analysis).
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_kernels_fundamentals.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): fundamentals numpy kernels`.

Out of scope: pandas adapters and calc nodes (M6.6, M6.7); currency handling (M6.1 `money`).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 alpha_nodes.kernels.fundamentals provides the eight kernels with the exact signatures, exported from alpha_nodes.kernels
- [ ] #2 Hand-value and edge tests pass for each kernel; non-finite input raises ValueError
- [ ] #3 Each kernel's docstring states its formula and nan rules
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
Worker: dispatch ctx_19e844b9e856, worktree task-50 (run run_af908de3f039)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: alpha_nodes.kernels.fundamentals with the eight kernels (safe_ratio, growth, cagr, mean_std, coefficient_of_variation, owner_earnings, sum_ratio, capitalised_value), exported from alpha_nodes.kernels; 41 tests. Commit b1f2110 (worktree task-50, single commit). pytest 851 passed, ruff and pyright clean.
Coordinator review: approved, no fix round. Matches the Interfaces and finance.md pinned conventions; docstrings state formulas and nan rules.
Rulings to check: mean_std uses max(min_n, 2) as the std threshold (ddof=1 needs 2); scalar kernels (growth, cagr, capitalised_value) don't check finiteness (spec required it for arrays only; a nan scalar propagates as nan). Open points: none.
<!-- SECTION:FINAL_SUMMARY:END -->
