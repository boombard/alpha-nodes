---
id: TASK-16
title: 'Aggregation v2: overlap discount, veto caps, subjective logic, calibration'
status: To Do
assignee: []
created_date: '2026-11-23T09:36:17Z'
labels:
  - core
  - sketch
milestone: m-7
dependencies:
  - TASK-9
  - TASK-14
references:
  - documentation/design/core.md
type: feature
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deferred from TASK-9 (human decision, 2026-11-23): TASK-9 ships the simple ShrunkMeanAggregator; this task holds the evidence-based upgrades. Sketch only. Detail it during M8 planning (TASK-15), once campaigns (M7) give many candidates and backtests give outcomes. Spec home: documentation/design/core.md, Verdicts and dossiers.

## Why (research summary, 2026-11-23)
- Simple pooled averages with shrinkage are a sound default without outcome data; learned weights rarely beat equal weights out of sample (Cooke classical-model studies; Davis-Stober et al. 2014).
- Shared information is double-counted when correlated sources are pooled (Satopää, Pemantle & Ungar, JASA 2016).
- Disagreement is a signal in its own right (Diether, Malloy & Scherbina, J. Finance 2002).
- Non-compensatory vetoes (ELECTRE-style) stop a severe weakness being averaged away (Bouyssou, "Outranking methods").
- Subjective logic models abstention, thin evidence and conflict explicitly (Kaplan, Ivanovska, Jøsang et al. 2018, arXiv 1805.01388).
- Ordinal-to-outcome calibration per rater (Dawid & Skene 1979), recalibrated pooling (Ranjan & Gneiting 2010).

## Scope sketch
1. **Overlap discount.** Each ok verdict's weight is multiplied by `discount_i = 1 / (1 + Σ_{j≠i} o(i, j))`.
   - Structural overlap from the plan graph: `o(i, j) = |upstream(i) ∩ upstream(j)| / |upstream(i)|` over each lens's transitive upstream nodes (directional: a lens contained in another is discounted more).
     - Example A, different aspects of one filing: quality {filings_raw, income_stmt, balance_sheet, quality_metrics}, governance {filings_raw, governance_section, board_metrics} give discounts 0.80 and 0.75.
     - Example B, L1 on filings+prices, L2 on filings only: L1 0.63, L2 0.50.
   - Measured overlap: with at least `min_candidates_for_correlation` (e.g. 30) candidates in a run or campaign, use the positive part of the correlation of lens `stance_mean`s across candidates instead.
   - Manual `overlap_overrides: [[lens_a, lens_b, value]]` for dependencies the graph can't see (same vendor, same news feed).
   - The dossier records each lens's discount and its source (structural, measured, override).
2. **Configurable veto caps** replacing VetoAggregator's fixed -2: rules by flag code, or by lens + stance + conviction, each with a `cap` on overall stance. The dossier records which rule applied and the citing verdict.
2a. **Bayesian k-shrink as an alternative policy:** `overall = Σw·s / (Σw + k)`, the M2 original. It was replaced as the default because a fixed k over-shrinks small panels; if revived, scale k with the panel (`k = κ·W_max`) and fit κ in calibration.
3. **Subjective-logic aggregator** as an optional, pluggable alternative: map (stance_mean, conviction, coverage) to evidence counts; weighted or averaging fusion; report expected value, uncertainty and conflict alongside the default. Compare both on the toy panel and the worked examples before promoting either.
4. **Calibration (needs outcomes, M8):** per-lens mapping from stance to realised outcome; a combiner shrunk toward equal weights; recalibrated output; always validated against the equal-weight baseline out of sample.

Depends on the TASK-6 follow-up adding `stance_mean`, `stance_spread` and `Provenance.stance_samples`, if that is accepted.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
