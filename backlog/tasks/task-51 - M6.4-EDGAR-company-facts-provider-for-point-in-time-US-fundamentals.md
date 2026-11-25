---
id: TASK-51
title: M6.4 EDGAR company-facts provider for point-in-time US fundamentals
status: In Review
assignee: []
created_date: '2026-11-25T08:17:58Z'
updated_date: '2026-11-25T23:50:32Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-49
references:
  - documentation/design/finance.md
type: feature
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`EdgarProvider`: point-in-time US annual fundamentals from SEC XBRL company facts, mapped to the canonical `fundamentals` schema through a curated `us-gaap` tag map, with filing dates as `known_at`. Registered in the catalog as `edgar`. After M6.1 (contracts); runs alongside M6.5 and M6.6. Spec: `documentation/design/finance.md` ("Fundamentals: datasets, providers and pinned conventions", Providers, Provider fallback, Data quality); `documentation/design/core.md` (Source store).

**Network:** the one sanctioned network use is running the new fixture recorder once. SEC requires a descriptive User-Agent: before recording, `ask` the coordinator for the value of `ALPHA_NODES_SEC_USER_AGENT` (the human provides it; never commit it, never hard-code it).

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/providers/edgar/__init__.py`
  - `packages/alpha_nodes/src/alpha_nodes/providers/edgar/provider.py`: `EdgarProvider`, `EDGAR_POLICY`
  - `packages/alpha_nodes/src/alpha_nodes/providers/edgar/companyfacts.py`: payload model, tag map, `normalise_companyfacts`
  - `packages/alpha_nodes/scripts/record_edgar_fixtures.py`
  - `packages/alpha_nodes/tests/fixtures/edgar/` (recorded, gzipped JSON) with a `README.md` (what, when, findings)
  - `packages/alpha_nodes/tests/edgar_replay.py`: a replay HTTP fake for tests (no network)
- Modify: `packages/alpha_nodes/src/alpha_nodes/catalog.py` (add the `edgar` factory, reading `FinanceSettings`)
- Test: `packages/alpha_nodes/tests/test_edgar_companyfacts.py`, `packages/alpha_nodes/tests/test_edgar_provider.py`
- Modify `documentation/design/finance.md` with findings that confirm or correct it (as TASK-31/32 did for yfinance).

## Interfaces
Consumes: `FUNDAMENTALS`, `FundamentalsSchema`, `FinanceSettings` (M6.1); `Provider` protocol, `ProviderCapabilities`, `RateLimitPolicy`, `FetchOutcome`, `WorkItem`, `RawResponse`, `NormalisedMeta`, `ProviderContext`, `SourceCatalog` (M4); `to_major` (units). HTTP via `curl_cffi.requests` (already a dependency); no new dependency.

Produces:
```python
# providers/edgar/companyfacts.py
COMPANYFACTS_NORMALISER_VERSION = "1"
class EdgarFactsPayload(BaseModel):     # stored verbatim as the raw payload
    symbol: str; cik: int
    facts: dict[str, Any]               # the company-facts JSON as served
TAG_MAP: dict[str, tuple[str, ...]]     # canonical line item -> us-gaap (or dei) tags, priority order
def normalise_companyfacts(payload: EdgarFactsPayload) -> pd.DataFrame
    # FundamentalsSchema columns + NormalisedMeta columns, known_at = filed_at (UTC midnight)
    # one row per (period_end, filed_at): form 10-K or 10-K/A, fp "FY"; flow items need a 350-380 day duration
    # per item the first TAG_MAP tag with a value; a later tag differing by > 1% -> suspect "tag_conflict:<item>"
    # check: total_assets vs total_liabilities + total_equity off by > 2% -> suspect "balance_mismatch"
    # capex positive; currency "USD" (facts in other units are ignored)

# providers/edgar/provider.py
EDGAR_POLICY = RateLimitPolicy(concurrency=2, per_second=5, burst=2, max_consecutive_empty=None, ...)
class EdgarProvider:                    # implements lensgraph.sources.Provider
    name = "edgar"
    def __init__(self, cache_dir: Path, clock: Clock | None = None, *, user_agent: str) -> None
        # ValueError when user_agent is blank
    # capabilities: datasets {"fundamentals"}, max_batch 1, EDGAR_POLICY, pit_reliable {"fundamentals": True}
    # entity: a Yahoo symbol. A symbol with an exchange suffix ("BP.L") -> empty, no request.
    # ticker -> CIK from SEC's company_tickers.json, cached at cache_dir/company_tickers.json for 7 days
    #   (Yahoo "BRK-B" style tickers map to SEC "BRK-B"); unknown ticker -> empty.
    # companyfacts without us-gaap annual facts (e.g. a 20-F/IFRS filer) -> empty
    # HTTP 429 / 403 -> rate_limited; connection failure / timeout -> unreachable; other HTTP or parse errors -> error

# catalog.py
CATALOG.providers["edgar"]   # factory: EdgarProvider(ctx.cache_dir, ctx.clock, user_agent=FinanceSettings().sec_user_agent)
                             # raises ValueError naming ALPHA_NODES_SEC_USER_AGENT when unset
```

## Steps
- [ ] Write the recorder and record once (after the coordinator gives the User-Agent): company facts for AAPL (September fiscal year), KO (December), and one US small cap, plus the matching subset of `company_tickers.json`. Store as gzipped JSON; record the date, URLs and findings in the fixtures README.
- [ ] Write the failing tests:
  - `test_edgar_companyfacts.py` (on the fixtures): `test_aapl_annual_periods_have_canonical_items` (at least 8 annual periods; revenue, net income, common equity, operating cash flow present in the latest), `test_known_at_is_filed_at`, `test_comparatives_from_later_10k_are_separate_rows` (one `period_end`, two `filed_at`), `test_capex_is_positive`, `test_balance_check_passes_on_aapl`, `test_ko_december_fiscal_year`.
  - Synthetic payloads built in the test (not fixtures): `test_tag_conflict_marks_suspect`, `test_quarterly_and_short_duration_facts_ignored`, `test_10k_amendment_adds_a_later_filing_row`, `test_no_usgaap_annual_facts_gives_empty_frame`.
  - `test_edgar_provider.py` (replay fake, `FakeClock`): `test_suffixed_symbol_is_empty_without_request`, `test_unknown_ticker_is_empty`, `test_ticker_map_cached_for_7_days`, `test_http_429_is_rate_limited`, `test_connection_error_is_unreachable`, `test_capabilities_and_breakers` (`max_consecutive_empty is None`, pit_reliable true), `test_blank_user_agent_rejected`, `test_catalog_factory_requires_user_agent`.
  - `test_edgar_provider.py::test_store_fallback_edgar_then_fake_yfinance`: a `DuckDBSourceStore` with chain `[edgar, fake]` serves AAPL from edgar and BP.L from the fake.
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_edgar_companyfacts.py packages/alpha_nodes/tests/test_edgar_provider.py -q`. Expected: FAIL.
- [ ] Implement; keep the tag map small (the line items the v1 calcs need), with a comment per item naming the alternatives considered.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): EDGAR company-facts provider for point-in-time US fundamentals`.

Out of scope: quarterly periods; 10-K text (`filings_text`, deferred); `ifrs-full` facts of foreign filers; yfinance fundamentals (M6.5).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 EdgarProvider maps recorded AAPL and KO company facts to FundamentalsSchema rows, one per (period_end, filed_at), known_at = filed_at
- [ ] #2 Tag priority is explicit; a conflicting lower-priority tag marks the row suspect (tag_conflict), balance mismatch marks suspect
- [ ] #3 Suffixed and unknown symbols are empty without a request; empty breaker off; 429/403 rate_limited; ticker map cached 7 days
- [ ] #4 catalog registers edgar; the factory fails naming ALPHA_NODES_SEC_USER_AGENT when unset; the UA is never committed
- [ ] #5 A store with chain [edgar, fake] serves AAPL from edgar and BP.L from the fallback; fixtures recorded once with a README
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
Worker: dispatch ctx_8c455556e912, worktree task-51 (Orca run run_09eee9a7786f)
2026-11-26: first worker_done failed (no SEC User-Agent; question timed out). Human supplied the UA; resumed as follow-up dispatch ctx_10ae7d5603c8.
Review round 1 sent (HEAD 379aa4e): total_debt excludes short-term borrowings and its LongTermDebtNoncurrent fallback changes meaning.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker summary: EdgarProvider (SEC company facts, ticker->CIK map cached 7 days, suffixed/unknown symbols empty without a request, 429/403 rate_limited, 404 empty, EDGAR_POLICY with empty breaker off, pit_reliable), companyfacts normaliser + curated TAG_MAP, replay fake, catalog 'edgar' factory (ValueError naming ALPHA_NODES_SEC_USER_AGENT), fixtures recorded live 2026-11-26 (AAPL, KO, LAKE; 4 requests; UA via env only, not in any file) with README findings, finance.md EDGAR note. pytest 923 passed, ruff and pyright clean. 5 commits 5e8aeea..8bddc0f: squash on landing. Review: 1 fix round. R1: total_debt was long-term debt only and its LongTermDebtNoncurrent fallback silently dropped current maturities (fixed: _compose_total_debt = LongTermDebt, else Noncurrent+Current, else Noncurrent alone with partial:total_debt suspect, plus first of ShortTermBorrowings/CommercialPaper; leases excluded; finance.md updated). Verdict: approve. Rulings: a period exists only where a full-year flow fact exists; total_equity and cash use first-tag fallback without tag_conflict; shares_outstanding from us-gaap CommonStockSharesOutstanding (null for KO), total_liabilities not derived (KO null, balance check skipped); SalesRevenueGoodsNet added for KO history; edgar_replay fixture in tests/conftest.py (outside Files, accepted; TASK-53 also edits conftest.py at a different spot). Open for the human: tag_conflict fires on AAPL D&A/interest in 24+12 of 57 rows and LAKE in 7, which may make suspect noisy; decide whether D&A/interest tag differences should count as conflicts.
<!-- SECTION:FINAL_SUMMARY:END -->
