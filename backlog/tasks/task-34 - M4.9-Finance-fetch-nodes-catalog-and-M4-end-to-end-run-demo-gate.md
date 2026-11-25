---
id: TASK-34
title: M4.9 Finance fetch nodes, catalog and M4 end-to-end run (demo gate)
status: In Progress
assignee: []
created_date: '2026-11-25T01:09:40Z'
updated_date: '2026-11-25T05:21:28Z'
labels:
  - finance
milestone: m-3
dependencies:
  - TASK-32
  - TASK-33
  - TASK-37
references:
  - documentation/design/finance.md
type: feature
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Finance end-to-end for M4 and its demo gate: the finance source catalog, `prices`/`profile`/`fx` fetch nodes, a run config over 10 UK/European tickers plus AAPL, and an offline e2e test replaying the recorded fixtures. After M4.7 and M4.8. Spec: milestone M4 demo gate; `documentation/design/finance.md` (Providers, market focus, Currency); `documentation/design/core.md` (Source store).

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/catalog.py`: `CATALOG` (`SourceCatalog`: `DATASETS` + `{"yfinance": YFinanceProvider factory}`)
  - `packages/alpha_nodes/src/alpha_nodes/nodes/__init__.py`, `packages/alpha_nodes/src/alpha_nodes/nodes/fetch.py`: `Prices`, `Profile`, `FxRates`
  - `packages/alpha_nodes/src/alpha_nodes/registry.py`: `build_registry()`
  - `runs/m4_prices.yaml`
  - `packages/alpha_nodes/tests/yf_replay.py`: a fixture-backed stand-in for `yfinance.Ticker` (counts calls)
- Modify: `documentation/design/finance.md` only if behaviour differs from it
- Test: `packages/alpha_nodes/tests/test_m4_e2e.py`

## Interfaces
Consumes: `DatasetFetch`, `DatasetFetchMany`, `SourceCatalog`, `ProviderContext`, `SourcesConfig`, `RunConfig`, `arun`, CLI (M4.8); `YFinanceProvider`, fixtures (M4.6, M4.7); `DATASETS`, `MINOR_UNITS` (M4.4).

Produces:
```python
# nodes/fetch.py
class Prices(DatasetFetch):  name = "prices";  dataset = "prices";  lookback_days: int = 3653   # >= 10 years
class Profile(DatasetFetch): name = "profile"; dataset = "profile"
class FxRates(DatasetFetchMany): name = "fx"; dataset = "fx"
    entities: list[str] = ["GBP", "EUR", "CHF", "SEK", "NOK", "DKK", "PLN"]; lookback_days: int = 3653
# registry.py
def build_registry() -> NodeRegistry            # Prices, Profile, FxRates
# catalog.py
CATALOG: SourceCatalog
```
`runs/m4_prices.yaml`: candidates BP.L, HSBA.L, VOD.L, SHEL.L, ULVR.L, ASML.AS, SAP.DE, MC.PA, NESN.SW, NOVO-B.CO, AAPL; targets `[prices, profile, fx]`; registry `alpha_nodes.registry:build_registry`; `sources: {catalog: alpha_nodes.catalog:CATALOG, providers: {prices: [yfinance], profile: [yfinance], fx: [yfinance]}}`.

## Steps
- [ ] Write the failing tests in `test_m4_e2e.py` (yfinance replaced by `yf_replay`, `FakeClock` during LSE trading hours on a day after the fixtures' last date; candidates = the fixture symbols):
  - `test_second_run_makes_no_yfinance_calls`
  - `test_gbp_minor_unit_normalised_in_run_output`: BP.L `prices` output in GBP with the `minor_unit` repair.
  - `test_live_bar_never_stored`: the replay serves a bar for "today"; the store has no fact for today and logs an `unsettled` attempt.
  - `test_suspect_rows_surface`: a replay symbol whose payload has one close ×100 (constructed in the test from a fixture, labelled as such) → that row is `suspect` in the node output and in `lensgraph sources status --suspect`.
  - `test_unknown_ticker_is_empty_not_failure`: an unknown symbol gives an empty `prices` frame, an `empty` attempt, and no refetch on run 2.
  - `test_fx_rates_cover_all_currencies`
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_m4_e2e.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Prepare the demo (do not run it in tests; network): write in the task notes the exact commands for the human:
  `uv run lensgraph run runs/m4_prices.yaml` twice, then `uv run lensgraph sources status --suspect`, then `uv run lensgraph run runs/m4_prices.yaml --offline`.
- [ ] Commit: `feat(alpha_nodes): prices/profile/fx fetch nodes, catalog and M4 end-to-end run`.

Out of scope: lenses and calcs on prices (M5), adjusted-close calc (M5), `data_quality` flags in lenses (M5).

**Demo gate (milestone M4):** fetching the 11 tickers twice makes network calls only the first time (attempt log); GBp tickers normalised; no live bar stored; suspect rows visible via `sources status --suspect`; the offline rerun succeeds.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Prices, Profile and FxRates nodes, CATALOG and build_registry exist; runs/m4_prices.yaml targets them over 10 UK/European tickers plus AAPL
- [ ] #2 Replayed e2e: the second run makes no yfinance calls; GBp normalised; no live bar stored; unknown ticker is empty and not refetched
- [ ] #3 A x100 row surfaces as suspect in the node output and in sources status --suspect; fx covers all seven currencies
- [ ] #4 Task notes give the exact demo commands for the human
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
Worker: dispatch ctx_13aafebdd418, worktree task-34
<!-- SECTION:NOTES:END -->
