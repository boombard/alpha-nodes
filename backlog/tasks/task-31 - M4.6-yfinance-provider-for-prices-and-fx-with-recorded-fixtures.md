---
id: TASK-31
title: M4.6 yfinance provider for prices and fx with recorded fixtures
status: To Do
assignee: []
created_date: '2026-11-25T01:09:28Z'
labels:
  - finance
milestone: m-3
dependencies:
  - TASK-29
references:
  - documentation/design/core.md
  - documentation/design/finance.md
type: feature
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`YFinanceProvider` for `prices` and `fx`: the only code that knows yfinance names, Yahoo symbols and Yahoo quirks. After M4.4 (parallel with M4.5). Spec: `documentation/design/finance.md`, "yfinance fetching and throttling" and "Data quality: yfinance quirks" (prices rows of the table); `documentation/design/core.md`, Source store. Follow the research there; where it says *unverified*, verify with the recorded fixtures and note the result in the task notes.

Network: tests never touch it. The fixture recorder below is the one sanctioned live use in this task: run it once, commit its output, and say in the notes when and with which yfinance version.

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/providers/__init__.py`
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/__init__.py`
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/provider.py`: `YFinanceProvider`, setup, error classification, symbol → MIC
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/history.py`: chart payload model, prices and fx normalisation, repairs and checks
  - `packages/alpha_nodes/scripts/record_yfinance_fixtures.py`: live recorder (not imported by tests)
  - `packages/alpha_nodes/tests/fixtures/yfinance/`: recorded payloads (JSON) + `README.md` listing symbols, ranges, date recorded and yfinance version
- Modify: `packages/alpha_nodes/pyproject.toml` (`yfinance[repair]==1.8.0`, `curl_cffi`)
- Test: `packages/alpha_nodes/tests/{test_yf_history,test_yf_provider}.py`

## Interfaces
Consumes: `Provider`, `ProviderCapabilities`, `RateLimitPolicy`, `WorkItem`, `FetchOutcome`, `RawResponse`, `Clock`, `GlobalFailure` (M4.1); `PRICES`, `FX`, `PriceSchema`, `FxSchema`, `to_major`, `markets.*` (M4.4).

Produces:
```python
# history.py
class YFHistoryPayload(BaseModel):      # the verbatim chart response, JSON-safe, stored as the raw payload
    symbol: str
    metadata: dict[str, Any]              # yfinance history_metadata (JSON-safe copy)
    columns: list[str]                    # as returned, e.g. Open High Low Close Adj Close Volume Dividends Stock Splits Repaired?
    index: list[str]                      # ISO timestamps with offset
    data: list[list[float | None]]
    requested_start: date; requested_end: date
def normalise_prices(payload: YFHistoryPayload, mic: str) -> pd.DataFrame   # PriceSchema + NormalisedMeta columns
def normalise_fx(payload: YFHistoryPayload) -> pd.DataFrame                 # FxSchema + NormalisedMeta columns
# provider.py
SUFFIX_MIC: dict[str, str]   # ".L": "XLON", ".PA": "XPAR", ".AS": "XAMS", ".BR": "XBRU", ".LS": "XLIS", ".IR": "XDUB",
                             # ".DE": "XETR", ".MI": "XMIL", ".MC": "XMAD", ".SW": "XSWX", ".ST": "XSTO", ".CO": "XCSE",
                             # ".OL": "XOSL", ".HE": "XHEL", no suffix: "XNYS" (US)
def symbol_mic(symbol: str) -> str          # ValueError naming an unknown suffix
def fx_symbol(currency: str) -> str         # "GBP" -> "GBPUSD=X"
YF_POLICY: RateLimitPolicy   # concurrency 4, per_second 2, burst 4, backoff (30, 60, 120, 240), jitter 0.25,
                             # max_rate_limit_episodes 3, max_unreachable 5, max_error_retries 2
class YFinanceProvider:      # Provider
    name = "yfinance"
    def __init__(self, cache_dir: Path, clock: Clock | None = None, *, min_window_days: int = 183) -> None
        # checks yfinance.HAS_CURL_CFFI (RuntimeError if missing), set_cache_location(cache_dir),
        # config.debug.hide_exceptions = False, config.network.retries = 2, timeout 15 s
    capabilities: ProviderCapabilities   # datasets {prices, fx}, max_batch 1, YF_POLICY, pit_reliable {prices: True, fx: True}
```
Semantics:
- `fetch`: one fresh `yf.Ticker(sym).history(start, end + 1 day, auto_adjust=False, actions=True, repair=True)` per item. The request is padded back to `min_window_days` before `interval.end` (repair context); coverage still records the requested interval.
- Outcomes: `YFRateLimitError` → `rate_limited`; `YFTzMissingError` → `empty`; `YFPricesMissingError` → `empty` when no timezone is known for the symbol, else `ok` with an empty payload; connection/timeout errors → `unreachable`; anything else → `error` with the message.
- `settled_through`: `markets.settled_through(symbol_mic(sym), clock.now())` for prices, `fx_settled_through` for fx. A live bar for today is therefore never a fact.
- `restated_before`: a split (non-zero `Stock Splits`) inside a request whose requested start is after the split date − 2 years → `restated_before = split date` (earlier closes are now split-adjusted differently).
- Prices repairs: currency from `metadata["currency"]` via `to_major`; minor units divide open/high/low/close/dividends by the factor (repair `"minor_unit"`); a true `Repaired?` → repair `"yf_price_repair"`.
- Prices checks (quality `suspect` + reason; value kept): close/previous close ≥ 50 or ≤ 0.02 → `"jump_x100"`; dividend / close > 0.25 → `"dividend_yield_gt_25pct"`; a bar on a non-session day → `"non_session_bar"`; a bar after ≥ 3 missing sessions → `"missing_sessions:<n>"`. Rejected: close ≤ 0 or NaN.
- `known_at` for prices = `markets.session_close(mic, date)`; for fx = end of that UTC day.
- `normaliser_version` per dataset: a string constant per normaliser; bump it when its behaviour changes.

Fixtures (recorded live by the script, committed): prices for BP.L, HSBA.L, VOD.L, ASML.AS, SAP.DE, NESN.SW, NOVO-B.CO, AAPL over 2 years ending on the recording date, plus one 5-day window containing a known split for one ticker (pick one, say which in the README); fx for GBP, EUR, CHF, DKK over 1 year. If a symbol fails, the README says so: never hand-edit payloads.

## Steps
- [ ] Write the recorder; run it once; commit the fixtures and README.
- [ ] Write the failing tests:
  - `test_yf_history.py` (fixtures only):
    - `test_gbp_minor_unit_repaired`: BP.L closes in GBP (≈ 1/100 of the payload values), `currency == "GBP"`, repairs contain `"minor_unit"`.
    - `test_eur_and_chf_unchanged`: ASML.AS EUR, NESN.SW CHF, no `minor_unit` repair.
    - `test_output_validates_against_schema` for every prices fixture and every fx fixture.
    - `test_x100_jump_marked_suspect`: a copy of a fixture with one close ×100 (constructed in the test, labelled as such) gives `"jump_x100"`.
    - `test_non_session_bar_marked_suspect` (constructed copy with a Sunday bar).
    - `test_known_at_is_session_close`
    - `test_fx_rate_is_usd_per_unit`: GBPUSD=X close > 1.
  - `test_yf_provider.py` (`yfinance.Ticker` monkeypatched with a stub that returns fixture frames or raises the real yfinance exception classes):
    - `test_exceptions_classified` (parametrised: rate limit, tz missing, prices missing with/without tz, connection error, other)
    - `test_live_bar_after_settled_cut_not_a_fact`: clock during LSE hours → `settled_through` is the previous session.
    - `test_request_padded_for_repair_context`
    - `test_split_in_top_up_sets_restated_before`
    - `test_capabilities_declared`
    - `test_missing_curl_cffi_raises` (monkeypatch `HAS_CURL_CFFI`)
- [ ] Run `uv run pytest packages/alpha_nodes -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): yfinance provider for prices and fx, with recorded fixtures`.

Out of scope: profile (M4.7), canary script (M4.7), fetch nodes and runs (M4.9).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Recorded yfinance 1.8.0 fixtures for the listed symbols are committed with a README; tests never touch the network
- [ ] #2 GBp prices are repaired to GBP with a minor_unit repair; EUR/CHF untouched; outputs validate against PriceSchema/FxSchema
- [ ] #3 x100 jumps, non-session bars, missing sessions and >25% dividend yields are marked suspect with reasons
- [ ] #4 yfinance exceptions map to rate_limited/empty/ok-empty/unreachable/error; settled_through excludes live bars; splits in top-ups set restated_before
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
