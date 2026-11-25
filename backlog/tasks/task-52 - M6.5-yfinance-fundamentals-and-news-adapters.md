---
id: TASK-52
title: M6.5 yfinance fundamentals and news adapters
status: To Do
assignee: []
created_date: '2026-11-25T08:17:58Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-49
references:
  - documentation/design/finance.md
type: feature
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
yfinance adapters for `fundamentals` (annual statements) and `news`, inside `YFinanceProvider`, with recorded fixtures and canary invariants. After M6.1 (contracts); runs alongside M6.4 and M6.6. Spec: `documentation/design/finance.md` ("Fundamentals: datasets, providers and pinned conventions"; Data quality quirk table rows for statements, capex, scale and `.info`; yfinance fetching and throttling).

**Network:** the one sanctioned network use is running the fixture recorder once, for the new stems only (`--only`), and the canary once to report.

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/fundamentals.py`: `YFStatementsPayload`, `payload_from_ticker_statements`, `normalise_fundamentals`
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/news.py`: `YFNewsPayload`, `normalise_news`
  - fixtures `packages/alpha_nodes/tests/fixtures/yfinance/fundamentals_<symbol>.json` and `news_<symbol>.json`
- Modify:
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/provider.py`: capabilities and dispatch for the two datasets
  - `packages/alpha_nodes/scripts/record_yfinance_fixtures.py`, `packages/alpha_nodes/scripts/canary.py`
  - `packages/alpha_nodes/tests/yf_replay.py` (replay statements, `.info` and news)
  - `packages/alpha_nodes/tests/fixtures/yfinance/README.md`
- Test: `packages/alpha_nodes/tests/test_yf_fundamentals.py`, `packages/alpha_nodes/tests/test_yf_news.py`, `packages/alpha_nodes/tests/test_yf_provider.py`
- Modify `documentation/design/finance.md` with findings that confirm or correct it (e.g. the capex sign, "only ~4 annual periods", whether statements carry a currency).

## Interfaces
Consumes: `FUNDAMENTALS`, `NEWS`, their schemas (M6.1); `YFinanceProvider`, `_classify`, `YF_POLICY`, `yf_replay` (M4); `to_major`.

Produces:
```python
# providers/yfinance/fundamentals.py
FUNDAMENTALS_NORMALISER_VERSION = "1"
class YFStatementsPayload(BaseModel):   # verbatim, JSON-safe
    symbol: str
    income: dict[str, Any]; balance: dict[str, Any]; cashflow: dict[str, Any]   # frame dumps (columns, index, data) of the yearly statements
    financial_currency: str | None      # .info financialCurrency
    info_net_income: float | None       # .info netIncomeToCommon, for the scale check
def normalise_fundamentals(payload: YFStatementsPayload) -> pd.DataFrame
    # FundamentalsSchema + NormalisedMeta; period_type "annual", filed_at null (no known_at column)
    # statements merged on period_end; a period column > 70% NaN in its statement is dropped
    # capex stored positive; minor-unit currency to major (values divided)
    # suspect "balance_mismatch" (> 2%); rejected "scale_mismatch" (ratio ~1e3 or ~1e6 vs info_net_income);
    # rejected "no_currency" when financial_currency is None

# providers/yfinance/news.py
NEWS_NORMALISER_VERSION = "1"
class YFNewsPayload(BaseModel): symbol: str; items: list[dict[str, Any]]   # Ticker.get_news(count=20) verbatim
def normalise_news(payload: YFNewsPayload) -> pd.DataFrame
    # NewsSchema + NormalisedMeta, known_at = published_at; items without an id or publication time are skipped

# provider.py
# capabilities.datasets += {"fundamentals", "news"}; pit_reliable False for both
# fundamentals fetch: yearly income_stmt, balance_sheet, cashflow + .info (financialCurrency, netIncomeToCommon)
#   all three statements empty -> error (transient, finance.md quirk table); unknown symbol -> empty (as profile)
# news fetch: get_news(count=20); [] -> ok with no items (a quiet week is not "unknown")
```

## Steps
- [ ] Extend the recorder and record `fundamentals_*` and `news_*` for BP.L (USD reporting), HSBA.L (a bank: no operating income or capex), VOD.L (EUR), BOOT.L (small cap), ASML.AS, SAP.DE, NESN.SW, NOVO-B.CO and AAPL. Note the findings in the fixtures README.
- [ ] Write the failing tests:
  - `test_yf_fundamentals.py` (fixtures): `test_bp_reports_usd_in_fundamentals`, `test_periods_are_annual_and_sorted`, `test_capex_positive_on_every_fixture`, `test_sparse_period_dropped` (synthetic payload), `test_balance_mismatch_suspect` (synthetic), `test_scale_mismatch_rejected` (synthetic, 1e3), `test_no_currency_rejected`, `test_bank_has_null_operating_items` (HSBA.L), `test_every_fixture_validates_against_schema`.
  - `test_yf_news.py`: `test_news_fixture_normalises` (ids unique, published_at tz-aware, known_at equals it), `test_items_without_id_skipped`, `test_empty_news_is_ok_empty_frame`.
  - `test_yf_provider.py`: `test_fundamentals_all_empty_statements_is_error`, `test_fundamentals_unknown_symbol_is_empty`, `test_capabilities_include_fundamentals_and_news_not_pit_reliable`.
  - Canary: add invariants (capex ≥ 0 after mapping; ≥ 3 annual periods; financialCurrency present for equities) and report them in `worker_done`.
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_yf_fundamentals.py packages/alpha_nodes/tests/test_yf_news.py packages/alpha_nodes/tests/test_yf_provider.py -q`. Expected: FAIL.
- [ ] Implement. Never read `.info` ratios (data quality principle 1); only `financialCurrency` and `netIncomeToCommon`.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): yfinance fundamentals and news adapters`.

Out of scope: quarterly statements; EDGAR (M6.4); analyst recommendations or price targets (never ingested, finance.md lens inputs).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 YFinanceProvider serves fundamentals (annual statements + financialCurrency) and news; pit_reliable false for both
- [ ] #2 Normalisation merges statements on period_end, drops >70% NaN periods, stores capex positive, converts minor units
- [ ] #3 Checks: balance_mismatch suspect, scale_mismatch and no_currency rejected; all-empty statements are a transient error
- [ ] #4 Fixtures recorded for the nine canaries incl. HSBA.L (bank); canary has fundamentals invariants; README findings recorded
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
