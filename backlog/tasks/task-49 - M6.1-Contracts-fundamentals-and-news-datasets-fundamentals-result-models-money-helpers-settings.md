---
id: TASK-49
title: >-
  M6.1 Contracts: fundamentals and news datasets, fundamentals result models,
  money helpers, settings
status: To Do
assignee: []
created_date: '2026-11-25T08:17:39Z'
labels:
  - finance
  - contracts
milestone: m-5
dependencies: []
references:
  - documentation/design/finance.md
type: feature
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Shared interfaces for M6: the canonical `fundamentals` and `news` datasets, the fundamentals result models the calc nodes return and the lenses cite, `NewsItem`, currency helpers that refuse to mix currencies without fx, finance settings (SEC User-Agent), and the two fetch nodes. It starts the milestone, alongside M6.2 (kernels) and M6.3 (TASK-25, critical inputs). Spec: `documentation/design/finance.md` (Datasets; "Fundamentals: datasets, providers and pinned conventions"; Currency; Data quality principle 2); `documentation/design/core.md` (Source store).

## Files
- Modify:
  - `packages/alpha_nodes/src/alpha_nodes/datasets.py`: `FundamentalsSchema`, `NewsSchema`, `FUNDAMENTALS`, `NEWS`; add both to `DATASETS`
  - `packages/alpha_nodes/src/alpha_nodes/metrics.py`: `PeriodWindow` and the fundamentals result models, `NewsItem`
  - `packages/alpha_nodes/src/alpha_nodes/conventions.py`: `FILING_LAG_DAYS`, `MAX_ANNUAL_PERIODS`
  - `packages/alpha_nodes/src/alpha_nodes/nodes/fetch.py`: `Fundamentals`, `News`
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/money.py`
  - `packages/alpha_nodes/src/alpha_nodes/settings.py`
  - `packages/alpha_nodes/src/alpha_nodes/reference.py`: `reference_day`
- Test: `packages/alpha_nodes/tests/test_datasets.py`, `packages/alpha_nodes/tests/test_metrics.py`, `packages/alpha_nodes/tests/test_money.py` (new), `packages/alpha_nodes/tests/test_fundamentals_store.py` (new)
- Modify `documentation/design/finance.md` only if behaviour differs from it.

## Interfaces
Consumes: `Dataset`, `DatasetFetch`, `DuckDBSourceStore` and its test fakes (M4); `FieldKind`, `is_major_iso`, `to_major` (`alpha_nodes.units`); `FxSchema` frames as `FxRates` returns them (an `entity` column per currency).

Produces:
```python
# datasets.py   (every column declares metadata={"kind": ...})
class FundamentalsSchema(pa.DataFrameModel):
    period_type: Series[str]          # isin ["annual"]; kind code
    period_end: Series[DateTime]      # kind date
    filed_at: Series[DateTime]        # nullable (yfinance); kind date
    currency: Series[str]             # reporting currency, major ISO (check like PriceSchema)
    revenue, operating_income, net_income, interest_expense, depreciation_amortization,
    operating_cash_flow, total_assets, total_liabilities, total_equity, common_equity,
    total_debt, cash: Series[float]   # nullable; kind money
    capex: Series[float]              # nullable, ge 0 (cash spent); kind money
    shares_diluted, shares_outstanding: Series[float]   # nullable, gt 0; kind shares
class NewsSchema(pa.DataFrameModel):
    id: Series[str]; published_at: Series[DateTime]      # tz-aware UTC
    headline: Series[str]; source, url, summary: Series[str]  # nullable; kind text
FUNDAMENTALS = Dataset(name="fundamentals", frame_schema=FundamentalsSchema,
    key_columns=("period_type", "period_end", "filed_at"), axis="none",
    ttl=timedelta(days=7), empty_ttl=timedelta(days=7))
NEWS = Dataset(name="news", frame_schema=NewsSchema, key_columns=("id",), axis="none",
    ttl=timedelta(days=1), empty_ttl=timedelta(days=7))

# conventions.py
FILING_LAG_DAYS = 90       # a period with no filing date counts as known 90 days after period_end
MAX_ANNUAL_PERIODS = 10

# metrics.py  (all frozen, extra="forbid"; None = can't be computed, never 0)
class PeriodWindow(BaseModel):
    periods: int = Field(ge=0); first_period_end: date | None; last_period_end: date | None
    suspect_periods: int = Field(ge=0)   # validator: <= periods
    currency: str | None                 # reporting currency; None when periods == 0
class ProfitabilityResult(PeriodWindow):
    roe_mean, roe_min, roe_std, op_margin_mean, op_margin_std, net_income_cv: float | None
    loss_years: int | None
class BalanceSheetResult(PeriodWindow):
    debt_to_equity, interest_cover, net_debt: float | None       # latest period; net_debt = total_debt - cash
class CashGenerationResult(PeriodWindow):
    owner_earnings, fcf: float | None                             # latest period, reporting currency
    fcf_conversion, share_count_cagr: float | None
class FundamentalTrendResult(PeriodWindow):
    revenue_growth_1y, revenue_cagr_3y, op_margin_change_1y, eps_growth_1y, fcf_growth_1y: float | None
class ValuationResult(PeriodWindow):
    price_date: date | None; close: float | None; trading_currency: str | None
    fx_rate: float | None        # reporting-currency units per trading-currency unit on price_date
    market_cap: float | None     # reporting currency
    earnings_yield, pe, owner_earnings_yield, value_low, value_high, price_to_value: float | None
class ValuationChangeResult(PeriodWindow):    # window of the "now" side
    date_now, date_then: date | None
    pe_now, pe_then, pe_change, earnings_yield_now, earnings_yield_then: float | None
class NewsItem(BaseModel):
    id: str; published_at: datetime; headline: str
    source: str | None; url: str | None; summary: str | None

# money.py
class CurrencyMismatch(ValueError): ...
def require_same_currency(*codes: str) -> str
    # the one code shared by all; CurrencyMismatch naming every distinct code otherwise
def usd_per_unit(fx: pd.DataFrame, currency: str, on: date, *, max_stale_days: int = 7) -> float | None
    # 1.0 for "USD"; else the last rate on or before `on` no older than max_stale_days, else None
def fx_factor(fx: pd.DataFrame, from_ccy: str, to_ccy: str, on: date) -> float | None
    # to_ccy units per from_ccy unit (1.0 when equal, without reading fx); None when a rate is missing

# reference.py
def reference_day(ctx: NodeContext) -> date
    # the day calcs are evaluated on: ctx.as_of, else the `sources` service clock's today (when the run has a store), else today (UTC)

# settings.py
class FinanceSettings(BaseSettings):   # env_prefix "ALPHA_NODES_", extra="ignore"
    sec_user_agent: str | None = None  # ALPHA_NODES_SEC_USER_AGENT; never committed

# nodes/fetch.py
class Fundamentals(DatasetFetch): name = "fundamentals"; dataset = "fundamentals"   # snapshot: no lookback
class News(DatasetFetch):         name = "news";         dataset = "news"
```

## Steps
- [ ] Write the failing tests:
  - `test_datasets.py`: `test_fundamentals_schema_accepts_canonical_frame` (two periods, one null `filed_at`), `test_fundamentals_rejects_negative_capex`, `test_fundamentals_rejects_minor_unit_currency` ("GBp"), `test_every_fundamentals_column_declares_a_kind`, `test_news_schema_requires_tz_aware_published_at`, `test_datasets_registry_has_fundamentals_and_news`.
  - `test_metrics.py`: `test_suspect_periods_cannot_exceed_periods`, `test_fundamentals_results_allow_none_fields`, `test_news_item_is_citable_by_id` (`citable_ids({"news": [item]})` contains `news[<id>]`).
  - `test_money.py`: `test_require_same_currency_raises_naming_codes`, `test_usd_per_unit_usd_is_one`, `test_usd_per_unit_takes_last_rate_on_or_before`, `test_usd_per_unit_none_when_stale_or_missing`, `test_fx_factor_cross_rate` (GBP->EUR = usd_per_unit(GBP)/usd_per_unit(EUR)), `test_fx_factor_same_currency_needs_no_fx` (empty fx frame).
  - `test_fundamentals_store.py` (a fake fundamentals provider in the test, `DuckDBSourceStore` on a tmp dir, `FakeClock`): `test_fundamentals_roundtrip_with_null_filed_at`; `test_two_filings_of_one_period_are_distinct_facts` (a 10-K and a later 10-K/A for the same `period_end`, `known_at` = their `filed_at`); `test_as_of_sees_only_filings_known_then`; `test_news_items_accumulate_across_snapshots` (second fetch after the TTL returns a different item set; both sets are served).
  - `test_money.py::test_reference_day_prefers_as_of_then_store_clock`
  - `test_money.py::test_finance_settings_reads_env` (monkeypatched `ALPHA_NODES_SEC_USER_AGENT`).
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_datasets.py packages/alpha_nodes/tests/test_metrics.py packages/alpha_nodes/tests/test_money.py packages/alpha_nodes/tests/test_fundamentals_store.py -q`. Expected: FAIL.
- [ ] Implement. If the store mishandles a nullable key column or a nullable datetime, stop and `ask` (that is a core change, not in Files).
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): M6 contracts: fundamentals and news datasets, fundamentals result models, money helpers, settings`.

Out of scope: providers (M6.4, M6.5), kernels (M6.2), adapters and calc nodes (M6.6, M6.7), lenses, registry wiring (M6.10).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 FundamentalsSchema, NewsSchema, FUNDAMENTALS and NEWS exist as specified and are in DATASETS; every column declares a field kind
- [ ] #2 PeriodWindow, the five fundamentals result models and NewsItem exist as specified (frozen, None allowed)
- [ ] #3 money helpers refuse mixed currencies (CurrencyMismatch) and never default a missing fx rate to 1.0; reference_day and FinanceSettings work as specified
- [ ] #4 The DuckDB store round-trips fundamentals with null filed_at, keeps two filings of one period as separate facts, and as-of sees only filings known then
- [ ] #5 Fundamentals and News fetch nodes exist
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
