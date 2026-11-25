---
id: TASK-34
title: M4.9 Finance fetch nodes, catalog and M4 end-to-end run (demo gate)
status: Done
assignee: []
created_date: '2026-11-25T01:09:40Z'
updated_date: '2026-11-25T05:38:49Z'
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
- [x] #1 Prices, Profile and FxRates nodes, CATALOG and build_registry exist; runs/m4_prices.yaml targets them over 10 UK/European tickers plus AAPL
- [x] #2 Replayed e2e: the second run makes no yfinance calls; GBp normalised; no live bar stored; unknown ticker is empty and not refetched
- [x] #3 A x100 row surfaces as suspect in the node output and in sources status --suspect; fx covers all seven currencies
- [x] #4 Task notes give the exact demo commands for the human
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
Worker: dispatch ctx_13aafebdd418, worktree task-34

Demo commands (network, run by the human): 'uv run lensgraph run runs/m4_prices.yaml' twice, then 'uv run lensgraph sources status --suspect', then 'uv run lensgraph run runs/m4_prices.yaml --offline'.

Demo gate run 2026-11-25 by the worker in task-34 (logs .lensgraph/m4-demo/ in that worktree): PARTIAL. Pass: second run makes no network calls for ok items; GBp normalised (BP.L 5.44 GBP); no live bar stored; suspect = 6 NOK fx_jump rows, no price suspects; no truncation on 10y. Fail: prices for SAP.DE and MC.PA fail in every run with 'normalise: TransactionException: Current transaction is aborted (please ROLLBACK)', so the offline rerun is 21/23 ok; failed items are retried each run. Also: CLI prints ok and exits 0 with failed nodes. Not signed off.

Fix 154c2b9 (human-approved, outside the original Files): DuckDB guessed the list type of the repairs/quality_reasons columns from a sample of rows. On ~2,540-bar histories where only the newest bar is repaired (SAP.DE, MC.PA) the sample held only empty lists, so it picked NULL[] and the insert failed. Unregistering the frame afterwards in the aborted transaction then replaced that error with 'transaction aborted'. Now the columns are typed explicitly as Arrow list<string> and the original error is re-raised. Tests: 2 store tests (toy) and 2 e2e tests with full 10y SAP.DE/MC.PA fixtures (~370KB each). 626 passed, ruff and pyright clean. Demo rerun: 23/23 ok online and offline, exit 0; suspect rows = 6 NOK fx_jump + 5 non_session_bar (SAP.DE German holidays 2017-18, MC.PA 2019-12-25, volume 0). Awaiting human sign-off.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: Prices/Profile/FxRates fetch nodes, build_registry, CATALOG, runs/m4_prices.yaml (11 tickers), yf_replay stand-in and test_m4_e2e.py (9 tests: second run 0 yfinance calls, offline rerun, GBp minor_unit repair, live bar not stored + unsettled attempt, x100 row suspect in output and sources status --suspect, unknown ticker empty and not refetched, fx covers 7 currencies, shipped config pinned). Commits f3990a2 + 9538888; pytest 620 passed, ruff and pyright clean. Coordinator review: ACs met; one fix round (pin shipped yaml in a test, import placement, Attributes docstrings) done. Open points/rulings: e2e overrides lookbacks (prices 700, fx 360) to fit 2-year fixtures, so the 10-year window is only exercised by the live demo; SEK/NOK/PLN fx replay the EUR fixture relabelled (coverage tested, not rate values); finance.md unchanged. Demo gate not yet run.

Landed 91b920e (squashed f3990a2..154c2b9) on main. M4 demo gate passed after the store fix: 23/23 nodes ok online and offline.
<!-- SECTION:FINAL_SUMMARY:END -->
