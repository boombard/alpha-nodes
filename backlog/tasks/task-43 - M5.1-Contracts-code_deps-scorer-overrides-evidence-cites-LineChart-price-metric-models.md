---
id: TASK-43
title: >-
  M5.1 Contracts: code_deps, scorer overrides, evidence cites, LineChart, price
  metric models
status: To Do
assignee: []
created_date: '2026-11-25T06:37:16Z'
labels:
  - core
  - finance
  - contracts
milestone: m-4
dependencies: []
references:
  - documentation/design/finance.md
  - documentation/design/core.md
type: feature
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Shared interfaces for M5: kernel-aware memo keys, run-tunable component scorers, extra evidence cites on deterministic claims, a generic `LineChart` value type, and the finance price-metric result models. Starts the milestone, in parallel with M5.2 (kernels). Spec: `documentation/design/finance.md` (Calculation layers; v1 lenses, price_behaviour, Pinned conventions); `documentation/design/core.md` (Nodes, Memoization, Deterministic lenses, Reporting).

## Files
- Modify:
  - `packages/lensgraph/src/lensgraph/node.py`: `Node.code_deps`, hashed by `code_version()`
  - `packages/lensgraph/src/lensgraph/deterministic.py`: `Component.evidence`, `DeterministicLens.scorer_overrides`
  - `packages/lensgraph/src/lensgraph/__init__.py`: export `LineChart`
  - `documentation/design/core.md`: Nodes (`code_deps`), Memoization (replace "the hash doesn't see helper functions" with the `code_deps` rule; keep `--invalidate` as the fallback), Deterministic lenses (`scorer_overrides`, `evidence`), Reporting (`LineChart` is a core value type; its view rendering arrives in M5.5)
- Create:
  - `packages/lensgraph/src/lensgraph/charts.py`: `LineChart`
  - `packages/alpha_nodes/src/alpha_nodes/metrics.py`: `PriceWindow`, `MomentumResult`, `TrendResult`, `VolatilityResult`, `DrawdownResult`
- Test: `packages/lensgraph/tests/test_node.py`, `packages/lensgraph/tests/test_deterministic.py`, `packages/lensgraph/tests/test_charts.py` (new), `packages/alpha_nodes/tests/test_metrics.py` (new)

## Interfaces
Consumes: `Node`, `DeterministicLens`, `Component`, `LinearScorer`, `LensAssessment` (M1/M2); `FileBlobStore`, `MemoryBlobStore` (M1.4).

Produces:
```python
# lensgraph/node.py
class Node:
    code_deps: ClassVar[tuple[Callable[..., Any] | ModuleType, ...]] = ()
    # code_version(): when code_deps is non-empty, also hashes inspect.getsource(d) for each d,
    # in declared order. With code_deps empty the hash is byte-identical to today's (no cache churn).

# lensgraph/deterministic.py
class Component:
    evidence: tuple[str, ...] = ()   # extra citable ids appended to the claim's cites, each only if it is in `citables`
class DeterministicLens:
    scorer_overrides: dict[str, LinearScorer] = {}   # component name -> scorer replacing the default;
                                                     # unknown names rejected like weight_overrides

# lensgraph/charts.py
class LineChart(BaseModel):          # frozen, extra="forbid"; a generic value a node may output and a claim may cite
    title: str
    x: list[date]
    series: dict[str, list[float | None]]   # series name -> y values; at least one series; each len(x)
    y_label: str | None = None

# alpha_nodes/metrics.py  (all frozen, extra="forbid")
class PriceWindow(BaseModel):
    bars: int = Field(ge=0)            # bars actually used
    start: date | None                 # first and last bar dates of the window; None when bars == 0
    end: date | None
    suspect_bars: int = Field(ge=0)    # bars in the window labelled `suspect`; validator: <= bars
class MomentumResult(PriceWindow):   total_return: float | None              # 12-1 total return; None if too short
class TrendResult(PriceWindow):      close: float | None; ma: float | None; pct_above_ma: float | None; ma_slope: float | None
class VolatilityResult(PriceWindow): annualised: float | None
class DrawdownResult(PriceWindow):   max_drawdown: float | None; peak_date: date | None; trough_date: date | None
```

## Steps
- [ ] Write the failing tests:
  - `test_node.py::test_code_deps_change_code_version`: two otherwise identical node classes, one with a function in `code_deps` → different `code_version()`; a module in `code_deps` also works.
  - `test_node.py::test_code_version_unchanged_without_code_deps`: for a node with no `code_deps`, `code_version()` equals the pre-change formula (recompute it in the test).
  - `test_deterministic.py::test_scorer_overrides_replace_default`: same input, overridden scorer → different component score and verdict score.
  - `test_deterministic.py::test_scorer_overrides_unknown_name_rejected`: `ValidationError` naming the known components.
  - `test_deterministic.py::test_evidence_cited_when_available`: claim cites `[source, "chart"]` when `chart` is an input.
  - `test_deterministic.py::test_evidence_skipped_when_not_citable`: with the evidence input `Absent`, the claim cites only `source` and the verdict is ok.
  - `test_charts.py::test_line_chart_series_length_mismatch_rejected`, `test_line_chart_needs_a_series`, `test_line_chart_roundtrips_blob_stores` (file and memory stores; `None` values survive).
  - `test_metrics.py::test_suspect_bars_cannot_exceed_bars`, `test_results_are_frozen`, `test_none_fields_allowed_for_short_history`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_node.py packages/lensgraph/tests/test_deterministic.py packages/lensgraph/tests/test_charts.py packages/alpha_nodes/tests/test_metrics.py -q`. Expected: FAIL.
- [ ] Implement, then update core.md as listed under Files.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(lensgraph,alpha_nodes): M5 contracts: code_deps, scorer overrides, evidence cites, LineChart, price metric models`.

Out of scope: kernels (M5.2), calc nodes (M5.3), the lens (M5.4), rendering `LineChart` in the run view (M5.5).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Node.code_deps is hashed into code_version; nodes without code_deps keep their exact current hash
- [ ] #2 DeterministicLens.scorer_overrides and Component.evidence work as specified; unknown override names rejected
- [ ] #3 LineChart validates series lengths and round-trips both blob stores; price metric models exist as specified
- [ ] #4 core.md updated (Nodes, Memoization, Deterministic lenses, Reporting)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
