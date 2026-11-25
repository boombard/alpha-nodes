---
id: TASK-48
title: >-
  M5.6 Register M5 nodes, 100-ticker price_behaviour run and M5 end-to-end (demo
  gate)
status: To Do
assignee: []
created_date: '2026-11-25T06:37:34Z'
updated_date: '2026-11-25T07:44:06Z'
labels:
  - finance
milestone: m-4
dependencies:
  - TASK-45
  - TASK-46
  - TASK-47
references:
  - documentation/design/finance.md
type: feature
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The finance end-to-end for M5 and its demo gate. It registers the price calc nodes and the price_behaviour lens, ships a 100-ticker UK/European run config, and adds an offline e2e test over the recorded yfinance fixtures. That test covers dossiers for every candidate, a report that shows charts and metrics, and a threshold change recomputing only the lens and the aggregator. After TASK-45 (M5.3), TASK-46 (M5.4) and TASK-47 (M5.5). Spec: milestone M5 demo gate; `documentation/design/finance.md` (market focus, v1 lenses, price_behaviour); `documentation/design/core.md` (Memoization, Run configuration).

## Files
- Modify: `packages/alpha_nodes/src/alpha_nodes/registry.py` (register `TotalReturn`, `Momentum`, `Trend`, `Volatility`, `Drawdown`, `PriceChart`, `PriceBehaviour`)
- Create:
  - `runs/m5_price_behaviour.yaml`
  - `packages/alpha_nodes/tests/test_m5_e2e.py`
- Modify (only if needed): `packages/alpha_nodes/tests/yf_replay.py`, `packages/alpha_nodes/tests/conftest.py`
- Modify: `documentation/design/finance.md` only if behaviour differs from it

## Interfaces
Consumes: everything TASK-43 (M5.1)–M5.5 produce; `Prices` and `CATALOG` (M4); `RunConfig`, `arun`, the CLI, `build_run_view` (M3/M4); `yf_replay` and the recorded fixtures (M4).

Produces:
```python
def build_registry() -> NodeRegistry   # M4's fetch nodes + the six M5 calc nodes + PriceBehaviour
```
`runs/m5_price_behaviour.yaml`:
- 100 unique UK/European candidates: about 40 LSE (`.L`), with the rest spread over Euronext (`.PA`, `.AS`, `.BR`, `.LS`, `.IR`), Xetra (`.DE`), Milan (`.MI`), Madrid (`.MC`), SIX (`.SW`), Stockholm (`.ST`), Copenhagen (`.CO`), Oslo (`.OL`) and Helsinki (`.HE`). Large and mid caps, mixed sectors, grouped by venue with a comment per group.
- `panel: {lenses: [price_behaviour]}` (default aggregator, **no reviewer**, so the demo makes no LLM calls)
- `nodes: {price_behaviour: {thresholds: [-0.6, -0.2, 0.2, 0.6]}}`, written out so the demo can edit it
- `sources` as in `runs/m4_prices.yaml`, prices and profile only (no fx: the price lens is ratio-based)

## Steps
- [ ] Write the failing tests in `test_m5_e2e.py` (yfinance replaced by `yf_replay`, `FakeClock` as in `test_m4_e2e.py`; candidates are the fixture symbols; lookbacks overridden where the 2-year fixtures need it; the 10-year SAP.DE and MC.PA fixtures give full windows):
  - `test_every_candidate_gets_a_price_behaviour_verdict`: one dossier per candidate; the 10y symbols have all five components; an unknown ticker gives a non-ok verdict and no exception.
  - `test_threshold_change_recomputes_only_lens_and_aggregator`: run, change `nodes.price_behaviour.thresholds`, rerun on the same store. In run 2 every calc and transform node is a cache hit, `price_behaviour` and `dossier` are not, and no yfinance calls are made.
  - `test_report_has_chart_and_metric_cites`: `build_run_view` on the run gives a momentum claim whose cites resolve to a `price_chart` entry of kind `chart` and a `momentum.total_return` entry.
  - `test_shipped_m5_config_is_valid`: the yaml loads as a `RunConfig` with 100 unique candidates, and its plan builds against `build_registry()`.
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_m5_e2e.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Prepare the demo (do not run it in tests; network). In the `worker_done` report, give the human the exact commands:
  1. `uv run lensgraph run runs/m5_price_behaviour.yaml` (live, first fetch of 100 tickers × 10y)
  2. open the report
  3. change the thresholds (give a one-line `sed` into a copy of the yaml)
  4. rerun the copy with `--offline`
  5. how to see that only `price_behaviour` and `dossier` re-executed (CLI output or `cache_hits` in the summary)
- [ ] Commit: `feat(alpha_nodes): register M5 nodes, 100-ticker price_behaviour run and M5 end-to-end`.

Out of scope: an AI reviewer in the demo; fx; campaign or universe logic (M7).

**Demo gate (milestone M5):** a live 100-ticker run gives an HTML report with a dossier per candidate, where claims drill down to the metrics and the price chart. Rerunning after a threshold change recomputes only the lens and the aggregator.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 build_registry registers the six M5 calc nodes and PriceBehaviour; runs/m5_price_behaviour.yaml has 100 unique UK/European tickers, no reviewer
- [ ] #2 Replayed e2e: every candidate gets a dossier with a price_behaviour verdict; an unknown ticker does not raise
- [ ] #3 A threshold change reruns only price_behaviour and dossier (all calc/transform nodes cache hits, no yfinance calls)
- [ ] #4 The run view resolves a momentum claim to a chart-kind price_chart and the momentum metric
- [ ] #5 worker_done gives the exact demo commands for the human
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
From TASK-47 landing: the chart kind and flat-model field tables have not been clicked through in a real browser (toy run cites no LineChart). Check price_chart and the metric tables in the demo report via Orca's browser.
<!-- SECTION:NOTES:END -->
