---
id: TASK-52
title: M6.5 yfinance fundamentals and news adapters
status: Done
assignee: []
created_date: '2026-11-25T08:17:58Z'
updated_date: '2026-11-26T01:05:53Z'
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
- [x] #1 YFinanceProvider serves fundamentals (annual statements + financialCurrency) and news; pit_reliable false for both
- [x] #2 Normalisation merges statements on period_end, drops >70% NaN periods, stores capex positive, converts minor units
- [x] #3 Checks: balance_mismatch suspect, scale_mismatch and no_currency rejected; all-empty statements are a transient error
- [x] #4 Fixtures recorded for the nine canaries incl. HSBA.L (bank); canary has fundamentals invariants; README findings recorded
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
Worker: dispatch ctx_b5e3a004af37, worktree task-52

Human review round 1 sent (dispatch ctx_d43424ea5a4b): currency null instead of XXX (datasets.py cleared), unknown_currency:<code> reason, sparse periods emitted as rejected sparse_period rows.

Human review round 1 resolved in 44ef844: FundamentalsSchema.currency nullable (null only on rows rejected for no_currency / unknown_currency:<code>; datasets.py cleared), XXX removed, sparse periods emitted as rejected sparse_period rows (fixtures now 4 ok + 1 rejected), scale check on latest non-sparse period, canary counts non-rejected periods and ignores sparse_period (not re-run live), store round-trip test with null currency. Commits 97478e7, 44ef844. Verdict: approve. Nit: _currency_is_major uses fillna('USD') to skip nulls (pandera already ignores NA by default).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: YFStatementsPayload/payload_from_ticker_statements/normalise_fundamentals and YFNewsPayload/normalise_news, both datasets wired into YFinanceProvider (pit_reliable false), recorder and canary extended (fundamentals invariants), 9 fundamentals + 9 news fixtures recorded live once (--only), canary run live once (exit 0; capex>=0, 4 annual periods, financialCurrency present on all nine), README and finance.md findings (capex negative on all nine; statements carry no currency; HSBA.L no operating income; oldest of 5 columns 85-98% NaN; netIncomeToCommon is TTM). Review: 0 rounds, no findings. Commit: 97478e7 (29 files, ~900 lines excluding fixtures). pytest 1049 passed, ruff and pyright clean. Verdict: approve. Open points / rulings to check: (1) rows rejected for no_currency carry currency 'XXX' (ISO 4217 no-currency) because the schema requires a major ISO code; (2) a period sparse in any statement is dropped from all three; (3) scale_mismatch and no_currency reject every row, balance_mismatch is per period; (4) an unrecognised financialCurrency code (to_major ValueError) is also reported as no_currency; (5) news items missing id, pubDate or title are skipped, duplicate ids keep the first; (6) process: the worker implemented before the red test run, so TDD was not followed for this task.

Landed 140f729 on main (squashed from 97478e7, 44ef844).
<!-- SECTION:FINAL_SUMMARY:END -->
