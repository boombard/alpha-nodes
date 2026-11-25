---
id: TASK-46
title: M5.4 price_behaviour deterministic lens
status: Done
assignee: []
created_date: '2026-11-25T06:37:27Z'
updated_date: '2026-11-25T07:42:48Z'
labels:
  - finance
milestone: m-4
dependencies:
  - TASK-43
references:
  - documentation/design/finance.md
type: feature
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The `price_behaviour` deterministic lens: five scored components over the M5 price metric models, with templated claims that cite the calc fields (and the price chart as evidence), plus a `data_quality` warn flag when suspect bars were used. After TASK-43 (M5.1) only. It is tested on hand-built result models, so it runs in parallel with M5.3. Spec: `documentation/design/finance.md` (v1 lenses, price_behaviour and Pinned conventions); `documentation/design/core.md` (Deterministic lenses).

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/lenses/__init__.py`
  - `packages/alpha_nodes/src/alpha_nodes/lenses/price_behaviour.py`
- Test: `packages/alpha_nodes/tests/test_price_behaviour_lens.py`

## Interfaces
Consumes: `DeterministicLens`, `Component` (with `evidence`), `LinearScorer`, `scorer_overrides`, `LensAssessment`, `Flag`, `LineChart` (M2, TASK-43 (M5.1)); `MomentumResult`, `TrendResult`, `VolatilityResult`, `DrawdownResult` (M5.1). The node names `momentum`, `trend`, `volatility`, `drawdown`, `price_chart` (implemented by M5.3; not imported here).

Produces:
```python
class PriceBehaviour(DeterministicLens):
    name = "price_behaviour"; lens_name = "price_behaviour"
    inputs = {"momentum": "momentum", "trend": "trend", "volatility": "volatility", "drawdown": "drawdown"}
    optional_inputs = {"price_chart": "price_chart"}
    input_weights = {"price_chart": 0.0}          # evidence only; does not count toward coverage
    components = [
        Component(name="momentum",    source="momentum.total_return",  scorer=LinearScorer(lo=-0.20, hi=0.40), weight=1.0,
                  claim_template="12-1 month total return {value:+.1%}", evidence=("price_chart",)),
        Component(name="trend",       source="trend.pct_above_ma",     scorer=LinearScorer(lo=-0.10, hi=0.10), weight=0.5,
                  claim_template="Close {value:+.1%} vs its 200-day average", evidence=("price_chart",)),
        Component(name="trend_slope", source="trend.ma_slope",         scorer=LinearScorer(lo=-0.20, hi=0.20), weight=0.5,
                  claim_template="200-day average rising {value:+.1%} a year"),
        Component(name="volatility",  source="volatility.annualised",  scorer=LinearScorer(lo=0.15, hi=0.45, higher_is_better=False), weight=0.5,
                  claim_template="Realised volatility {value:.0%} a year"),
        Component(name="drawdown",    source="drawdown.max_drawdown",  scorer=LinearScorer(lo=-0.60, hi=-0.15), weight=0.5,
                  claim_template="Max drawdown {value:.0%} over the window"),
    ]
    # assess(): the DeterministicLens result, plus Flag(severity="warn", code="data_quality", text=<which inputs, how many suspect bars>,
    #           cites=[f"{n}.suspect_bars" for each of momentum/trend/volatility/drawdown with suspect_bars > 0]) when any is > 0.
```
These defaults are a starting point, to be calibrated by the M8 backtest. Thresholds, weights and scorers stay run-tunable through the inherited params (`thresholds`, `weight_overrides`, `scorer_overrides`).

## Steps
- [ ] Write the failing tests (fixtures build the result models directly; a `LineChart` fixture for `price_chart`):
  - `test_strong_uptrend_is_strongly_bullish` (momentum 0.5, pct 0.15, slope 0.3, vol 0.15, dd -0.10 → stance 2, all five components)
  - `test_crash_is_strongly_bearish`
  - `test_middling_stock_is_neutral` (each value at its scorer's midpoint → score 0, stance 0)
  - `test_missing_component_is_skipped` (`momentum.total_return=None` → four components, status ok)
  - `test_all_values_none_abstains`
  - `test_suspect_bars_raise_data_quality_flag` (cites only the inputs with suspect bars)
  - `test_no_flag_without_suspect_bars`
  - `test_claims_cite_price_chart_when_present` and `test_claims_without_price_chart` (chart `Absent` → claims cite only their sources; coverage unaffected)
  - `test_overrides_change_the_verdict` (`thresholds`, `weight_overrides` and `scorer_overrides` set as params)
  - `test_lens_reads_only_calc_nodes` (`PriceBehaviour.all_inputs()` values are exactly the five calc node names)
  - `test_claim_texts_render` (e.g. "12-1 month total return +25.0%")
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_price_behaviour_lens.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): price_behaviour deterministic lens`.

Out of scope: registering the lens (M5.6); calibrating defaults (M8); coverage dropping for short history (TASK-25).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 PriceBehaviour has the specified inputs, components, default scorers, weights and claim templates
- [x] #2 Suspect bars raise a data_quality warn flag citing the affected inputs' suspect_bars
- [x] #3 Claims cite price_chart as evidence only when present; missing components skipped; all missing abstains
- [x] #4 thresholds, weight_overrides and scorer_overrides change the verdict as params
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
Worker: dispatch ctx_0938ae3c3037, worktree task-46 (run run_3fc22c1f4db5)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: PriceBehaviour deterministic lens (5 components with the specified scorers, weights and claim templates; price_chart optional, evidence only, input weight 0; data_quality warn flag added in an assess() override that calls super().assess(), citing <input>.suspect_bars for each input with suspect bars). 13 tests (all specified plus test_chart_does_not_change_coverage). pytest 780 passed, ruff and pyright clean.
Coordinator review: matches ACs 1-4, Files and Interfaces; docstrings present and meaningful. One fix round: an out-of-scope ruff-format reflow of test_m4_e2e.py was reverted (e4adda6). Diff vs main is now only the 3 task files.
Open points: 3 commits (feat, test fix, revert) - squash on landing. Rulings: flag text 'Suspect price bars used in: momentum (2 suspect bars), ...'; the flag is also added to abstained verdicts (harmless).

Landed 2a2879a on main (squashed).
<!-- SECTION:FINAL_SUMMARY:END -->
