# EDGAR recorded fixtures

Recorded live on **2026-11-26** by `packages/alpha_nodes/scripts/record_edgar_fixtures.py` (4 requests:
SEC's `company_tickers.json` and `data.sec.gov/api/xbrl/companyfacts/CIK<cik>.json` for three
companies). The files are the responses exactly as served, gzipped (`mtime=0`). Never hand-edit; re-run
the script (`--force` to overwrite) and re-commit to refresh. Tests read them through
`tests/edgar_replay.py` and never touch the network. The SEC User-Agent came from
`ALPHA_NODES_SEC_USER_AGENT` and is not stored in any file (the responses do not echo request headers).

| File | What |
|---|---|
| `company_tickers.json.gz` | the subset of SEC's ticker map for AAPL (CIK 320193), KO (21344), LAKE (798081) |
| `companyfacts_AAPL.json.gz` | Apple, fiscal year ends late September |
| `companyfacts_KO.json.gz` | Coca-Cola, December |
| `companyfacts_LAKE.json.gz` | Lakeland Industries (small cap), fiscal year ends 31 January |

URLs: `https://www.sec.gov/files/company_tickers.json`,
`https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` (and `CIK0000021344`, `CIK0000798081`).

## Findings (confirm or correct finance.md)

Rows below are `normalise_companyfacts` output (annual 10-K/10-K/A facts, flow items 350-380 days).

| Symbol | rows | distinct `period_end` | first .. last period | periods with 2 or more filings |
|---|---|---|---|---|
| AAPL | 57 | 20 | 2007-09-29 .. 2026-09-26 | 19 of 20 |
| KO | 51 | 19 | 2007-12-31 .. 2025-12-31 | 17 of 19 |
| LAKE | 36 | 18 | 2011-01-31 .. 2026-01-31 | 14 of 18 |

- **The design holds:** one fetch returns every filing, and each 10-K re-reports two to three prior years, so most
  periods have two or three rows with different `filed_at`. `known_at = filed_at` gives true as-of queries.
- **A 10-K carries more than the year:** its facts include fourth-quarter (about 90 day) durations with `fp == "FY"`, and
  instants at other dates. Only the 350-380 day duration filter, and requiring a full-year flow fact before a period
  exists, keep these out.
- **Tags change over time.** Apple's revenue is `SalesRevenueNet` until 2018, then
  `RevenueFromContractWithCustomerExcludingAssessedTax`; Coca-Cola's is `SalesRevenueGoodsNet` until 2016, then
  `Revenues`. The tag map lists all of them in priority order.
- **Coca-Cola never tags `Liabilities`** and has no `CommonStockSharesOutstanding`; `total_liabilities` is derived
  from `LiabilitiesAndStockholdersEquity` minus the NCI-inclusive equity and `shares_outstanding` from issued minus
  treasury shares (both recorded in `repairs`), so its balance check now runs and passes.
- **Older comparative periods lack the balance sheet:** a 10-K balance sheet has two year-ends but the income statement
  three, so the oldest comparative row of a filing has null balance-sheet items; a later filing's row has them.
- **Different tags in one filing are usually different measures, not disagreements.** With every lower-priority tag
  treated as a synonym, AAPL (24 depreciation and 12 interest rows) and LAKE (7) were flagged `tag_conflict` on normal
  filings. `TAG_MAP` now splits each item into synonyms (conflict-checked) and fallbacks (different scope, used only
  when no synonym has a value, recorded as `fallback:<item>=<tag>` in `repairs`). No `balance_mismatch` on any of the
  three.
- `dei` `EntityCommonStockSharesOutstanding` is a cover-page count at the filing date, so it is not used for period-end
  shares.

## Measurement of the tag rules, 2026-11-26

One-off run (script and downloads kept outside the repo) of `normalise_companyfacts` on 24 US filers: the three above
plus MSFT, XOM, CVX, JNJ, PFE, JPM, WFC, C, MET, ALL, DUK, NEE, O, PLD, WMT, HD, TGT, PG, HBB, GE, BA (an NATH request
found no ticker in SEC's map). Fiscal years: January (LAKE, WMT, HD, TGT), June (MSFT, PG), September (AAPL), the rest
December. 1,151 rows. "Old" is the first rule (every later tag a synonym; total_debt composed), "new" the
synonym/fallback split with the gap-filling identities.

| Item | `tag_conflict` rows old -> new | rows using a fallback or derivation (new) |
|---|---|---|
| revenue | 126 -> 27 (after the round-3 reclassification below) | 282 |
| net_income | 383 -> 0 | 37 |
| depreciation_amortization | 193 -> 0 | 373 |
| operating_cash_flow | 63 -> 0 | 109 |
| interest_expense | 18 -> 0 | 145 |
| capex | 0 -> 0 | 132 |
| total_equity / cash | 0 -> 0 | 334 / 246 |
| total_debt | 0 -> 0 | 318 (27 are `partial:total_debt`, suspect; after the round-3 and round-4 debt paths) |
| total_liabilities | 0 -> 0 | 142 derived |
| shares_outstanding | 0 -> 0 | 253 issued-treasury, 21 dei cover |

`balance_mismatch`: 0 before and after. Rows with any suspect: **55.3% -> 4.4%** (13.6% before the round-3 revenue and
debt changes, 8.9% before round 4). Worst companies, new (old) suspect rate: TGT 37% (98%), GE 32% (84%), JNJ 14% (35%),
PG 6% (100%), CVX 4% (45%). Null rate over all rows before -> after: shares_outstanding 53.1% -> 29.3%, total_liabilities 49.0% ->
36.7%; depreciation_amortization 10.3% and interest_expense 18.9% are unchanged (null where the tag is absent).

- **Revenue** (round 3): `Revenues` and `SalesRevenueNet` are the synonyms; the ASC 606 tags and `SalesRevenueGoodsNet`
  are fallbacks (`Revenues` is total revenue incl. leasing and finance income, which is why BA and GE differed from the
  ASC 606 tag). The 27 conflicting rows left are `Revenues` vs `SalesRevenueNet` (TGT 18, GE 6, PG 3).
- **`partial:total_debt`** (27 rows after round 4, from 81: GE 14, JNJ 7, CVX 2, others) is the other suspect reason:
  older filings that tag a non-current debt figure without any current portion. Round 4 uses `DebtCurrent` (all current
  debt) as the current part of a non-current figure when it is tagged, and a complete composition always beats a partial
  one.
- **`LongTermDebtAndCapitalLeaseObligations` is non-current**: for Duke (and others tagging both) `LongTermDebt` equals
  it plus its current tag exactly (2018: 54.53 = 51.12 + 3.41). Chevron tags the same non-current figure under
  `...IncludingCurrentMaturities` too (2022: 21.38 under both), so that tag is only used when the plain one is absent.
  For CVX 2025 the round-3 composition gave 43.1bn (39.78 + 2.35 + 0.98), undercounting short-term debt; with
  `DebtCurrent` (round 4) it is 39.78 + 10.92 = **50.7bn**, the balance-sheet figure.

Latest row of each filer only (newest `period_end`, latest `filed_at`; 23 filers with rows, XOM is empty), null rate and
who, after round 3:

| Item | null in latest row | filers |
|---|---|---|
| total_debt | 1/23 (4%) | O (tags `NotesPayable` 25.0bn + `LoansPayable` 1.7bn, not mapped) |
| total_liabilities | 1/23 (4%) | TGT |
| shares_outstanding | 1/23 (4%) | HBB |
| depreciation_amortization | 2/23 (9%) | MET, MSFT |
| capex | 6/23 (26%) | JPM, MET, NEE, O, PLD, WFC |
| interest_expense | 9/23 (39%) | ALL, BA, C, GE, JPM, NEE, O, WFC, AAPL |
| operating_income | 9/23 (39%) | ALL, C, CVX, GE, JNJ, JPM, O, PFE, WFC (no `OperatingIncomeLoss`; banks and insurers report pre-tax income, noninterest income and expense) |

Before round 3, total_debt was null for 5/23 (CVX, JPM, MET, O, KO). Round 4 leaves this table unchanged.
- Still-null `shares_outstanding` in a filer's latest row: only HBB (it tags `CommonStockSharesOutstanding` only up to
  2016 and has no issued count or cover count in companyfacts). Older null rows are comparative periods whose balance
  sheet a later 10-K does not repeat, and filers without a treasury tag. No multi-class filing was met in this sample,
  so `multi_class:shares_outstanding` is untested on real data.
- **XOM's company facts hold only 10-Q facts** (no 10-K rows), so it normalises to an empty frame and the provider
  answers `empty` (the store then falls back to the next provider).
