---
id: TASK-57
title: >-
  M6.10 Register M6 nodes, mixed-region fundamentals run and M6 end-to-end (demo
  gate)
status: To Do
assignee: []
created_date: '2026-11-25T08:18:00Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-51
  - TASK-52
  - TASK-53
  - TASK-54
  - TASK-55
  - TASK-56
  - TASK-61
references:
  - documentation/design/finance.md
type: feature
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The M6 end-to-end and its demo gate. It registers the M6 nodes and lenses, ships a mixed UK/European/US run config on the `dev` profile, adds an offline e2e over the recorded yfinance and EDGAR fixtures with a `FunctionModel`, and a small script that compares a rubric run with a `buffett_persona` run. After M6.4–M6.9. Spec: milestone M6 demo gate; `documentation/design/finance.md` ("Fundamentals: ..."; v1 lenses 2 and 3; Known data limitations); `documentation/design/core.md` (Memoization, Variants, Run configuration).

## Files
- Modify:
  - `packages/alpha_nodes/src/alpha_nodes/registry.py`: register `Fundamentals`, `News`, `AnnualFundamentals`, `Profitability`, `BalanceSheet`, `CashGeneration`, `FundamentalTrend`, `Valuation`, `ValuationChange`, `RecentNews`, `QualityValue`, `PriceVsFundamentals`
- Create:
  - `runs/m6_fundamentals.yaml`
  - `packages/alpha_nodes/scripts/compare_variants.py`
  - `packages/alpha_nodes/tests/test_m6_e2e.py`
- Modify (only if needed): `packages/alpha_nodes/tests/conftest.py`, `packages/alpha_nodes/tests/yf_replay.py`, `packages/alpha_nodes/tests/edgar_replay.py`
- Modify `documentation/design/finance.md` only if behaviour differs from it.

## Interfaces
Consumes: everything M6.1–M6.9 produce; M4/M5 nodes, `CATALOG`, `RunConfig`, `arun`, the CLI, the run index and `build_run_view`.

Produces:
```python
def build_registry() -> NodeRegistry   # M4 + M5 nodes + the twelve M6 nodes and lenses

# scripts/compare_variants.py  (click; reads the run index and blobs only, never the network)
#   uv run python packages/alpha_nodes/scripts/compare_variants.py RUN_A RUN_B [--lens quality_value] [--store PATH]
#   prints per candidate: status, stance and conviction in each run, and the cited input names;
#   then a summary: stance agreement (exact and within 1), mean |stance difference|, and cites per input for each run
def compare(store_root: Path, run_a: str, run_b: str, lens: str = "quality_value") -> VariantComparison
    # reads both runs' dossiers from the run index; VariantComparison is a pydantic model the CLI prints
```
`runs/m6_fundamentals.yaml`:
- 15 candidates: 5 US (AAPL, KO, and three more large caps), 5 UK (BP.L, HSBA.L, ULVR.L, DGE.L, BOOT.L), 5 European (ASML.AS, SAP.DE, NESN.SW, NOVO-B.CO, MC.PA), grouped with comments.
- `panel: {lenses: [price_behaviour, quality_value, price_vs_fundamentals]}`, default aggregator, no reviewer; `llm_profile` left at the default `dev`.
- `sources.providers`: `prices`, `profile`, `fx` and `news` from `[yfinance]`; `fundamentals: [edgar, yfinance]`.
- A header comment with the demo commands, the `ALPHA_NODES_SEC_USER_AGENT` and `ANTHROPIC_API_KEY` requirements, and how to make the persona copy (`nodes.quality_value.variant: buffett_persona`).

## Steps
- [ ] Write the failing tests in `test_m6_e2e.py` (yfinance and EDGAR replayed, `FakeClock`, a `FunctionModel` that answers with valid cites chosen from the ids in the user message and counts its calls; `ALLOW_MODEL_REQUESTS = False`):
  - `test_every_candidate_gets_three_verdicts`: one dossier per fixture candidate with price_behaviour, quality_value and price_vs_fundamentals verdicts; AAPL's fundamentals come from edgar, BP.L's from yfinance (provider recorded per fact).
  - `test_uk_european_coverage_lower_than_us`: quality_value coverage and dossier confidence are lower for a yfinance-only name (≈4 periods) than for AAPL (EDGAR, ≥ 8 periods).
  - `test_bank_runs_without_operating_items`: HSBA.L gets non-failed verdicts.
  - `test_unknown_ticker_abstains_without_llm_calls`: no fundamentals → both AI lenses abstain with the critical-input reason; the model counter does not move for it.
  - `test_variant_change_reruns_only_quality_value_and_dossier`: rerun with `nodes.quality_value.variant: buffett_persona` on the same store: no provider calls, model calls = number of candidates with fundamentals, every other node's output hash identical.
  - `test_report_resolves_ai_cites`: in `build_run_view`, a quality_value claim cite resolves to a field entry (e.g. `profitability.roe_mean`) and a news cite to its item.
  - `test_compare_variants_on_two_runs`: `compare` over the two runs gives one row per candidate and agreement in [0, 1].
  - `test_shipped_m6_config_is_valid`: the yaml loads, has 15 unique candidates and builds a plan against `build_registry()`.
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_m6_e2e.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Prepare the demo (not run in tests: network and a real LLM). In `worker_done`, give the human the exact commands:
  1. `export ALPHA_NODES_SEC_USER_AGENT=...` and `ANTHROPIC_API_KEY` (already set for M2 if so)
  2. `uv run lensgraph run runs/m6_fundamentals.yaml` (live; prints the run id)
  3. open the report; where to look for UK/European vs US coverage and confidence
  4. make the persona copy (one-line `sed`) and run it with `--offline` (fetches from the store; LLM calls are live)
  5. `uv run python packages/alpha_nodes/scripts/compare_variants.py <rubric run> <persona run>`
- [ ] Commit: `feat(alpha_nodes): register M6 nodes, mixed-region fundamentals run and M6 end-to-end`.

Out of scope: an AI reviewer in the demo; campaigns (M7); as-of fundamentals backtests (M8).

**Demo gate (milestone M6):** a mixed UK/European/US run on the `dev` profile; UK/European dossiers show lower coverage and confidence; a persona vs rubric comparison run.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 build_registry registers the twelve M6 nodes and lenses; runs/m6_fundamentals.yaml has 15 unique US/UK/European tickers on dev, no reviewer
- [ ] #2 Replayed e2e: three verdicts per candidate; AAPL fundamentals from edgar, BP.L from yfinance; UK/European coverage and confidence below the US name
- [ ] #3 An unknown ticker's AI lenses abstain without model calls; a variant change reruns only quality_value and dossier
- [ ] #4 compare_variants.py compares two runs' quality_value verdicts from the run index
- [ ] #5 worker_done gives the exact demo commands for the human
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
