---
id: TASK-32
title: M4.7 yfinance profile and live canary script
status: Done
assignee: []
created_date: '2026-11-25T01:09:29Z'
updated_date: '2026-11-25T04:54:02Z'
labels:
  - finance
milestone: m-3
dependencies:
  - TASK-31
references:
  - documentation/design/core.md
  - documentation/design/finance.md
type: feature
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add `profile` to `YFinanceProvider` and write the live canary script. After M4.6. Spec: `documentation/design/finance.md`, "yfinance fetching and throttling" (Profile cost), Data quality (principles 1, 2, 5; the `.info`, share-count and currency rows), market focus (dual listings: ISIN).

Network: as in M4.6, the recorder and the canary are the only live code; tests use the committed fixtures.

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/profile.py`: profile payload model and normalisation
  - `packages/alpha_nodes/scripts/canary.py`: live canary (exit code 1 on drift)
- Modify:
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/provider.py`: `profile` in capabilities and `fetch`/`normalise`
  - `packages/alpha_nodes/scripts/record_yfinance_fixtures.py`: also records profiles
  - `packages/alpha_nodes/tests/fixtures/yfinance/` (+ README)
  - `documentation/design/finance.md`: "Verified by recorded fixtures" notes from the canary probes below
- Test: `packages/alpha_nodes/tests/test_yf_profile.py`

## Interfaces
Consumes: M4.6's provider, `YFHistoryPayload`, `symbol_mic`, fixture layout; `PROFILE`, `ProfileSchema`, `to_major` (M4.4).

Produces:
```python
# profile.py
class YFProfilePayload(BaseModel):      # verbatim, JSON-safe
    symbol: str
    info: dict[str, Any]                  # Ticker.info
    isin: str | None                      # Ticker.isin; None when Yahoo returns "-" or nothing
def normalise_profile(payload: YFProfilePayload, mic: str) -> pd.DataFrame   # ProfileSchema + NormalisedMeta, one row
# canary.py
#   uv run python packages/alpha_nodes/scripts/canary.py [--symbols ...]
#   live-fetches the canary set through YFinanceProvider (no store), normalises, and compares invariants with the
#   fixtures: columns and dtypes, currency and repairs, close within 0.5x-2x of the fixture's last overlapping close,
#   profile currencies unchanged. Prints one line per symbol; exit 1 if any drifted.
```
Semantics:
- Mapping: `longName`→name (fallback `shortName`), `country`, `sector`, `industry`, `sharesOutstanding`, `firstTradeDateEpochUtc`→listing_date, `longBusinessSummary`, `financialCurrency`→reporting_currency, `currency`→trading_currency via `to_major` (repair `"minor_unit"` when it was a minor unit), exchange = `symbol_mic`. No Yahoo ratios or market cap are ingested (principle 1).
- Checks: missing or non-positive `sharesOutstanding` → suspect `"no_shares"`; `reporting_currency != trading_currency` is fine (BP.L) and not flagged; missing name → rejected.
- Profile fetch outcome classification reuses M4.6's.
- Canary set (finance.md): BP.L, HSBA.L, VOD.L, ASML.AS, SAP.DE, NESN.SW, NOVO-B.CO, AAPL, plus one `.L` line quoted in USD or EUR, one UK small-cap and one European small-cap. Choose the last three with the recorder, confirm their currencies from the recorded payload, and list them in the README.

**Added 2026-11-25 (defensive review of the yfinance downloads; findings feed TASK-37):**
- Recorder: also record 2-year **prices** for the three new canaries (the USD/EUR `.L` line and the two small caps). Add an `--only <names>` option and record only the new files; never re-record the existing TASK-31 price/fx fixtures (their tests depend on them). For every prices fixture the README lists the counts of missing sessions, zero-volume days, duplicate dates and non-session bars (computed by the recorder), so TASK-37 can set its gap threshold from real illiquid-name data.
- Canary health check: before the canary set, fetch AAPL over the last 5 days. A 404, empty answer or error prints `yahoo unhealthy: ...` and exits **2** (distinct from drift, exit 1).
- Canary request count: count the HTTP requests each `history()` call makes (first sight of a symbol vs a cached one) by wrapping the request method of yfinance's shared curl_cffi session (find the hook; say which in the README), and print them. The limiter assumes one request per item; record the real numbers in the README and finance.md, and say whether `repair=True` triggers extra downloads.
- Canary concurrency: `--concurrency N` (default 4) runs the fetches through a thread pool as the scheduler does; report any errors such as SQLite "database is locked" from yfinance's tz cache or crumb errors, and record the result in the README.

## Steps
- [ ] Extend the recorder; record profiles for the canary set; commit.
- [ ] Write the failing tests:
  - `test_bp_reports_usd_trades_gbp`: trading GBP (repaired from GBp), reporting USD.
  - `test_profile_validates_for_every_fixture`
  - `test_dual_listing_has_isin` for a listing whose fixture has one (say which in the test).
  - `test_no_yahoo_ratios_ingested`: output columns are exactly the schema's plus meta.
  - `test_missing_shares_marked_suspect` (constructed copy)
  - `test_profile_in_capabilities_and_fetch_outcomes_classified`
  - `test_canary_compare_flags_unit_drift`: the canary's pure comparison function, given a fixture frame and a ×100 copy, reports drift (the script's network part is not tested).
- [ ] Run `uv run pytest packages/alpha_nodes -q`. Expected: FAIL.
- [ ] Implement; run the canary once live (with `--concurrency 4`) and paste its output, including the request counts and the health check line, into the task notes.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): yfinance profile and live canary script`.

Out of scope: fundamentals/news/screen (M6/M7); the store and runs (M4.9).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Profile fixtures recorded for the canary set (incl. USD/EUR .L line and two small caps, listed in the README)
- [x] #2 normalise_profile maps trading (major unit) and reporting currencies, ISIN and shares; no Yahoo ratios or market cap ingested
- [x] #3 Missing shares marked suspect; missing name rejected; profile in capabilities with outcome classification reused
- [x] #4 canary.py compares live data with fixtures and exits 1 on drift; its comparison function is unit-tested
- [x] #5 Recorder adds small-cap/.L-line price fixtures without re-recording existing ones; README lists gap/zero-volume/duplicate/non-session counts; canary has a health check (exit 2), HTTP request counts per history() call and a concurrency mode, with results in README and finance.md
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
Worker: dispatch ctx_479cd1dcb02e, worktree task-32

Canary live run (2026-11-25, --concurrency 4, worker-reported): yahoo healthy; all 11 symbols ok; exit 0. First-sight requests prices/profile: BP.L 4/4, HSBA.L 4/4, VOD.L 5/4, ASML.AS 4/4, SAP.DE 4/4, NESN.SW 3/4, NOVO-B.CO 4/3, AAPL 2/4, VUSD.L 4/4, BOOT.L 4/4, ALCLS.PA 4/4. Warm concurrent pass: prices 2 (NESN.SW 1), profile 2 each. History requests BP.L, HSBA.L: repair=True 3, repair=False 1. Second live run after review fixes: cold and warm concurrent passes, all 11 ok, no lock/crumb/rate-limit errors, exit 0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: `profile` added to YFinanceProvider (YFProfilePayload, payload_from_ticker, normalise_profile, shared `_classify` for fetch outcomes); canary.py (health check exit 2, drift exit 1, per-call HTTP request counts via curl_cffi Session.request wrap, cold + warm --concurrency passes, repair request probe); recorder --only (default records only missing files; TASK-31 fixtures untouched) and price stats; profiles for 11 canaries; prices for VUSD.L, BOOT.L, ALCLS.PA and illiquid BMT.L. Commits 87c6a7f, 6889704, 5f8ab9d, 6a90365 (review fixes). pytest 536 passed, ruff clean, pyright 0 errors. Canary live: 11/11 ok, exit 0.

Coordinator review: ACs 1-5 met. One feedback round, all applied: stub `.info` without currency -> `empty` at fetch (an unrecognised currency -> `error`), so normalise can't raise inside the store's ensure; ISIN shape + ISO 6166 check digit, invalid -> None + suspect `bad_isin`; cold concurrent canary pass; price_stats moved to providers/yfinance/stats.py with a constructed-payload test; illiquid AIM fixture BMT.L (213/506 zero-volume bars, 0 missing sessions: Yahoo carries closes forward, so zero volume, not gaps, is the no-trade signal - input for TASK-37); RequestCounter.install docstring.

Findings recorded in finance.md / README: `.info` has `firstTradeDateMilliseconds`, not `firstTradeDateEpochUtc`; Ticker.isin is "-" for most non-US symbols and wrong-but-well-formed for ASML.AS (AR...); history costs 3-5 requests first sight, 1-2 warm; repair=True adds 2 for GBp; profile 3-4 first sight, 2 warm; limiter's one-request-per-item assumption undercounts (TASK-37 should weight).

Rulings to check: (1) DESIGN CHANGE: finance.md now says the profile ISIN is a hint, never a join key - the market-focus plan to de-duplicate dual listings by ISIN needs another source (M7). (2) test_yf_provider.py edited outside Files (capabilities assertions). (3) listing_date from firstTradeDateMilliseconds (EpochUtc kept as fallback). (4) Canaries: VUSD.L (USD ETF - no shares, so suspect no_shares), BOOT.L, ALCLS.PA (EUR quote, USD reporting). (5) Missing trading currency raises in normalise (backstop); bad financialCurrency -> reporting None + suspect; profile pit_reliable=False; known_at NaT. (6) test_dual_listing_has_isin uses AAPL (only well-formed ISIN fixture). (7) Recorder default now skips existing files. (8) Canary windows = fixture end - 30 days.

Open points: "cold" concurrency only relocates tz/cookie cache files; the in-memory crumb survives, so a brand-new process's first concurrent requests aren't covered. Exit-2 health path not exercised live. Rejected (no-name) profile rows store name "".

Landed bcc49b2 (squashed) on main
<!-- SECTION:FINAL_SUMMARY:END -->
