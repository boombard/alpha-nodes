---
id: TASK-44
title: 'M5.2 Numpy kernels: returns, rolling statistics, risk'
status: Done
assignee: []
created_date: '2026-11-25T06:37:17Z'
updated_date: '2026-11-25T06:54:57Z'
labels:
  - finance
milestone: m-4
dependencies: []
references:
  - documentation/design/finance.md
type: feature
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first `alpha_nodes.kernels`: atomic numpy functions for returns, rolling statistics and risk, each with its own tests (hand-computed values, edge cases, invariants, TA-Lib oracle where an equivalent exists). This is the bottom layer of the user's calculation design: kernels know nothing of pandas, dates or nodes. It has no task dependencies and runs in parallel with M5.1. Spec: `documentation/design/finance.md`, Calculation layers (read the kernel rules and NaN policy closely) and v1 lenses, price_behaviour, Pinned conventions; Technical analysis and TA-Lib; `documentation/reference/ta-lib/` for SMA, LINEARREG_SLOPE, STDDEV.

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/kernels/__init__.py` (re-exports the public kernels)
  - `packages/alpha_nodes/src/alpha_nodes/kernels/_validate.py`: the shared input checks (1-D, float64, finite, positive where required, window ≥ 1, equal lengths)
  - `packages/alpha_nodes/src/alpha_nodes/kernels/returns.py`
  - `packages/alpha_nodes/src/alpha_nodes/kernels/rolling.py`
  - `packages/alpha_nodes/src/alpha_nodes/kernels/risk.py`
- Test: `packages/alpha_nodes/tests/test_kernels_returns.py`, `test_kernels_rolling.py`, `test_kernels_risk.py` (flat, like the other alpha_nodes tests; shared fixtures such as a seeded random-walk price array go in `packages/alpha_nodes/tests/conftest.py`)
- Modify: `packages/alpha_nodes/tests/conftest.py` (fixtures only)

## Interfaces
Consumes: numpy; `talib` (dev dependency, tests only, never imported by `src`).

Produces (all arrays 1-D float64; every function documents its formula; invalid input raises `ValueError` naming the argument):
```python
# kernels/returns.py
def simple_returns(x: np.ndarray) -> np.ndarray                 # len n-1: x[1:] / x[:-1] - 1; x > 0
def log_returns(x: np.ndarray) -> np.ndarray                    # len n-1: diff(log x); x > 0
def total_return_index(close: np.ndarray, dividends: np.ndarray) -> np.ndarray
    # len n; TR[0] = 1, TR[t] = TR[t-1] * (close[t] + dividends[t]) / close[t-1]; close > 0, dividends >= 0, equal lengths
def skip_return(x: np.ndarray, lookback: int = 252, skip: int = 21) -> float
    # x[-1-skip] / x[-1-lookback] - 1; nan if len(x) < lookback + 1; requires 0 <= skip < lookback
# kernels/rolling.py
def sma(x: np.ndarray, window: int) -> np.ndarray               # len n; first window-1 values NaN
def rolling_std(x: np.ndarray, window: int, ddof: int = 1) -> np.ndarray   # len n; leading NaN; requires window > ddof
def linreg_slope(x: np.ndarray, window: int) -> np.ndarray      # len n; OLS slope of each trailing window on 0..window-1; leading NaN; window >= 2
# kernels/risk.py
def realised_volatility(returns: np.ndarray, periods_per_year: int = 252, ddof: int = 1) -> float
    # std(returns, ddof) * sqrt(periods_per_year); nan if len(returns) <= ddof
def drawdown(x: np.ndarray) -> np.ndarray                       # len n; x / running max(x) - 1, all <= 0; x > 0
def max_drawdown(x: np.ndarray) -> float                        # min(drawdown(x)); 0.0 if never below a prior peak; nan if empty
def drawdown_extent(x: np.ndarray) -> tuple[int, int]           # (peak index, trough index) of the max drawdown; earliest trough on ties;
                                                                # (i, i) for the last running-max index when there is no drawdown; ValueError if empty
```
Kernel input with NaN or inf raises (gaps are handled in the frame adapters, M5.3). Too-short input gives `nan` (scalar kernels) or an all-NaN array (rolling kernels), never an exception.

## Steps
- [ ] Invoke `test-driven-development`. Write the failing tests:
  - Hand values: `test_total_return_index_hand_value` (close [100, 101, 99], dividends [0, 0, 2] → [1, 1.01, 1.01]); `test_skip_return_hand_value` (x = arange(1, 300.0) → x[-22]/x[-253] - 1); `test_max_drawdown_hand_value` ([1, 2, 1, 3, 1.5] → -0.5) and `test_drawdown_extent_earliest_trough_on_tie` (→ (1, 2)); `test_realised_volatility_hand_value` (3 returns, computed by hand in the test with ddof=1 and periods 252).
  - Edge cases: `test_skip_return_nan_when_short`, `test_rolling_kernels_all_nan_when_short`, `test_realised_volatility_nan_when_too_few`, `test_max_drawdown_nan_when_empty`, `test_kernels_reject_non_finite` (parametrised over every kernel), `test_kernels_reject_non_positive_prices`, `test_kernels_reject_2d_input`, `test_total_return_index_rejects_length_mismatch`, `test_bad_window_rejected`.
  - Invariants (seeded random walks, parametrised): `test_max_drawdown_scale_invariant`, `test_drawdown_never_positive`, `test_monotone_series_has_zero_drawdown`, `test_sma_of_constant_is_constant`, `test_linreg_slope_of_line_is_its_slope`, `test_constant_growth_has_zero_volatility`, `test_log_and_simple_returns_agree` (exp(log_returns) - 1 == simple_returns).
  - TA-Lib oracles (500-bar seeded random walk; `np.testing.assert_allclose(..., rtol=1e-10, equal_nan=True)`): `test_sma_matches_talib` (windows 20 and 200), `test_linreg_slope_matches_talib` (window 20), `test_rolling_std_matches_talib_population` (ddof=0 vs `talib.STDDEV(x, timeperiod, nbdev=1)`), `test_realised_volatility_matches_talib_rescaled` (STDDEV × √(n/(n−1)) × √252 on the last n returns).
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_kernels_returns.py packages/alpha_nodes/tests/test_kernels_rolling.py packages/alpha_nodes/tests/test_kernels_risk.py -q`. Expected: FAIL.
- [ ] Implement, vectorised (no Python loops over bars; `numpy.lib.stride_tricks.sliding_window_view` or cumulative sums are fine).
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): numpy kernels for returns, rolling statistics and risk`.

Out of scope: pandas adapters and calc nodes (M5.3); any kernel the price_behaviour lens does not need (EMA, RSI, ...).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Kernels exist with the exact signatures; pure numpy, no pandas imports in alpha_nodes.kernels
- [x] #2 Hand-value, edge-case and invariant tests pass for every kernel; non-finite input raises, short input gives nan
- [x] #3 TA-Lib oracle tests pass for sma, linreg_slope, rolling_std (ddof=0) and realised_volatility (rescaled)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run pytest` passes (whole workspace)
- [x] #2 `uv run ruff check` and `uv run pyright` are clean
- [x] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [x] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_00e73ddd91c0, worktree task-44
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: all 11 kernels + _validate, test-first, in commit dad7908 (worktree task-44). pytest 753 passed, ruff and pyright clean. TA-Lib oracles for sma (20, 200), linreg_slope (20), rolling_std ddof=0 and rescaled realised_volatility.
Review verdict: approved, no fix round. Signatures match the Interfaces exactly; vectorised (sliding_window_view, centred-t OLS slope); kernels import no pandas; ValueError names the argument; short input gives nan/all-NaN.
Rulings to check: (1) linreg_slope oracle adds atol=1e-12 beside rtol=1e-10 (TA-Lib running-sum drift on near-zero slopes); (2) log/simple agreement uses rtol=1e-9, atol=1e-14; (3) the cross-kernel validation tests sit in test_kernels_returns.py through an ALL_KERNELS dict; (4) skip_return, realised_volatility and total_return_index also validate lookback, periods_per_year, ddof and negative dividends (stricter than specified). Open points: none.

Landed 61b0c8c on main
<!-- SECTION:FINAL_SUMMARY:END -->
