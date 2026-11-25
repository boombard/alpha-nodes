# `alpha_nodes`: the finance domain

Built on `lensgraph`. Its first use is **equity universe construction**: deciding which
tickers belong in a universe and why, with filtering and optimisation downstream.
Stance labels: −2 strong bearish … +2 strong bullish.

**Market focus (user, 2026-11-25): UK and European equities.** Campaigns, demos and
canaries target LSE plus the main European venues (Euronext Paris/Amsterdam/Brussels/
Lisbon/Dublin, Xetra, Milan, Madrid, SIX Swiss, Nasdaq Nordic and Oslo). US tickers stay
supported, mainly so EDGAR can give point-in-time fundamentals backtests. Australia is
dropped.

- Many venues means many trading calendars and timezones: the trading-day check and the
  "settled" cut-off are per exchange (e.g. via `exchange_calendars`: XLON, XPAR, XAMS,
  XETR, XMIL, XMAD, XSWX, XSTO, XCSE, XOSL, XHEL…).
- Many currencies: GBP/GBp, EUR, CHF, SEK, NOK, DKK, PLN. GBp remains the only
  minor-unit repair in scope.
- Dual listings (e.g. Shell, Unilever on `.L` and `.AS`): `profile` records the
  primary listing / ISIN so universe construction can de-duplicate one company.

## Datasets (canonical schemas)

Each dataset has one canonical schema (pandera or pydantic) in `alpha_nodes.datasets`.
Every downstream node relies on that schema and never on provider-specific columns.

| Dataset | Coverage axis | Notes |
|---|---|---|
| `prices` | trading date | daily OHLCV + dividends + split ratio, major units, **no adjusted close** (see Prices and point-in-time). ≥10y history needed for 12-1 momentum + 200-day trend + risk |
| `profile` | none (snapshot) | name, country, exchange, currency, sector, industry, shares outstanding (**no market cap**: computed as price × shares), listing date, business summary |
| `fundamentals` | fiscal period (annual/quarterly) | income/balance/cash-flow line items with `period_end`, `filed_at` where available |
| `news` | published time | id, published_at, headline, source, url, summary. Providers may only serve recent items |
| `filings_text` | filing date | e.g. 10-K "Business" + "Risk factors" sections (US) |
| `screen` | none | population listing for campaigns (ticker, country, exchange, sector, mcap, volume) |
| `fx` | date | daily FX rates to USD, for comparable absolute thresholds |

LLM for AI lenses: the `dev` model profile by default (Claude Haiku 5.5, low effort), with
`local` (Ollama) and `quality` (Sonnet 5.5) profiles available. See core.md, Model profiles.

Sector taxonomy: use one canonical sector list (yfinance's sector names, which are
GICS-like) mapped in the provider. Treat it as a stratum key.

## Providers

- **`YFinanceProvider`**: prices, profile, fundamentals (no filing dates →
  `pit_reliable=false`), news (recent only), screen (`yf.screen` + `EquityQuery`, regions
  e.g. `gb`, `de`, `fr`, `nl`, `ch`, `se`).
  - The only place that knows yfinance column names, quirks, throttling, retry and
    error classification.
  - Must classify: rate-limit → backoff/retry; unknown ticker → `empty`; repeated
    connection failure → `GlobalFailure`.
  - See "yfinance fetching and throttling" below for how it declares capabilities.
- **`EdgarProvider`**: US fundamentals from SEC XBRL "company facts" (has filing dates →
  `pit_reliable=true`), and 10-K text sections. It must send a descriptive User-Agent as
  SEC requires. That value comes from local config/env, not committed.
- Provider per dataset is chosen in run config:
  `providers: {prices: yfinance, fundamentals: [edgar, yfinance]}`. A list means fallback
  order, and the provider used is recorded per fact.
- Adding a provider = one adapter class + one mapping per dataset it supports.
- Fetch nodes are **generic**: one `DatasetFetch(dataset="prices")` node type
  parameterised by dataset, not a node class per provider × dataset.

### yfinance fetching and throttling

Researched 2026-11-25 by reading the yfinance 1.8.0 source (not executed); items marked
*unverified* are to be confirmed by recorded fixtures or the canary script. All of this
lives inside `YFinanceProvider`; the core only sees the declared capabilities (core.md,
Source store).

- **Pin `yfinance==1.8.0`** with the `[repair]` extra. Fail at startup if `curl_cffi` is
  unavailable (`HAS_CURL_CFFI`); otherwise yfinance silently falls back to plain
  `requests`, which Yahoo may block. Don't pass a `requests_cache` session (rejected).
- **No batching: declare `max_batch=1`.** `yf.download`/`yf.Tickers` still make one chart
  request per ticker in a thread pool, force one date range for all tickers, and toggle
  global error-hiding state per ticker (racy). Only prices have a chart endpoint;
  profile, statements and news are per ticker anyway.
- **Calls**: a fresh `Ticker(sym).history(start=, end=, auto_adjust=False, actions=True,
  repair=True)` per work item, via `asyncio.to_thread` under the core limiter. Set
  `yf.config.debug.hide_exceptions = False` once. `auto_adjust=False` is required: the
  adjusted default rewrites past closes on every dividend, which breaks append-only facts.
- **Caches**: `yf.set_cache_location(<store dir>/yfinance)` before any fetch (tz, cookie
  and ISIN caches move together). Sharing it across processes is *unverified*.
- **Profile cost**: `.info` costs 2 requests and `fast_info` is not cheaper (it pulls 1y
  of prices). Take trading currency and exchange timezone from each chart response's
  `history_metadata`; fetch `.info` only for sector, shares, `financialCurrency`, ISIN,
  with the 90-day profile TTL.
- **Exceptions**: `YFRateLimitError` → rate-limit outcome (yfinance has already retried
  once with a fresh cookie). `YFTzMissingError` → unknown ticker → `empty`.
  `YFPricesMissingError` is raised both for unknown tickers and for a valid ticker with
  no bars in the range, so it is `empty` for the entity only when no timezone is known,
  otherwise an `ok` empty interval. A 404 may cost 2–3 requests (crumb refresh;
  *unverified*).
- **Settled cut-off**: Yahoo returns a live bar for today while the market is open.
  Settled = last trading day before today in the exchange's timezone, or today once
  the exchange's close + 30 min has passed.
- **Top-ups and repair**: a short top-up window gives `repair=True` little context. When a
  top-up shows a new split/dividend, refetch a wider window (3–6 months) for that ticker.
- **Starting rate-limit policy** (Yahoo publishes no limits; tune from the attempt log):
  concurrency 4, ~2 requests/s with burst 4, provider-wide pause on rate limit with
  backoff 30/60/120/240 s + jitter, `GlobalFailure` after 3 consecutive rate-limit
  episodes or 5 consecutive connection failures; `yf.config.network.retries = 2`,
  15 s timeout. Unknown tickers are `empty` with a ~7-day TTL. Anecdotally Yahoo blocks
  are per IP and last ~1.5–24 h, so stopping beats hammering.

**Verified by recorded fixtures (2026-11-25, yfinance 1.8.0; see
`packages/alpha_nodes/tests/fixtures/yfinance/README.md`):**

- The cache setter is `yfinance.cache.set_cache_location`, and `HAS_CURL_CFFI` is in
  `yfinance._http`. The per-request timeout is the `timeout=` argument of `history`
  (`config.network` has only `proxy` and `retries`).
- An unknown symbol first answers a bare `HTTPError 404` (status on `exc.response`), and
  `YFTzMissingError` only after yfinance has cached the missing timezone (third call). Both
  are classified `empty`; the 404 is not left to retries.
- `YFPricesMissingError` for a weekend range on a known symbol is raised with the timezone
  known, giving an `ok` empty interval.
- LSE bars come back in GBp, with yfinance's own `Repaired?` flag true on most rows, so
  `yf_price_repair` is common there and is not by itself a quality signal.

### Data quality: yfinance quirks and how we handle them

Researched 2026-11-23: the old repo's fixtures and code, plus yfinance issues and changelog.
Five principles:

1. **Don't ingest Yahoo's derived ratios.** `.info` ratios (debt/equity, dividendYield,
   P/E, P/B, margins) are where most unit and currency bugs live. Ingest raw ingredients
   instead: statement line items, prices, dividends, share counts. Compute every ratio in
   our own calc nodes. This is the guard-rail principle applied to data.
2. **Units and currency are data, not convention.**
   - Each canonical field declares its kind: `money`, `per_share`, `shares`, `ratio`
     (always a fraction), `count`.
   - Monetary columns are stored in **major units** with an explicit `currency` column.
   - Every instrument carries **two currencies**: `trading_currency` (prices, market cap)
     and `reporting_currency` (statements; Yahoo's `financialCurrency`). Examples: BP.L
     trades in GBp and reports in USD; some European listings trade in local currency
     and report in EUR or USD.
   - Calc helpers that combine price-side and statement-side money **must convert through
     `fx` as of the date**. Mixing currencies raises rather than silently dividing.
3. **Repair what's certain, flag what isn't** (core source-store repairs/checks). Every
   repair is recorded per row.
4. **Keep raw responses**, so a newly found quirk is fixed by `renormalise`, not by
   re-downloading.
5. **Pin the yfinance version.** Contract tests run on recorded fixtures of awkward tickers.
   A separate live *canary* script (not part of the test suite) re-fetches the canaries and
   diffs invariants, to catch format changes like the `dividendYield` switch.
   - Canary set: BP.L (GBp vs USD reporting), HSBA.L, VOD.L, one `.L` line quoted in
     USD or EUR, ASML.AS, SAP.DE, NESN.SW (CHF), NOVO-B.CO (DKK), AAPL (US/EDGAR path),
     one small-cap UK and one small-cap European.

| Quirk | Evidence | Handling |
|---|---|---|
| Ratios silently in percent vs fraction: `debt_to_equity` 102.63 (= 1.03×) next to fractional margins; `dividendYield` now a percent while `trailingAnnualDividendYield` is a fraction | alpha-capture fixture `metrics_aapl.json`; its `fundamentals.py`/`growth.py` scored raw 102.63 as extreme leverage; yfinance reports (2025–26) | principle 1: compute ratios ourselves. If a Yahoo ratio is ever ingested, it needs a declared source unit + a cross-check against our own computation |
| GBp/GBX (pence) vs GBP: 100× errors in prices, market cap, dividends (dividends often in pounds while prices are in pence) | yfinance #280, #2866, #2924; `fast_info.market_cap` 100× bug (PR #3047, Nov 2026); alpha-capture fixture HSBA.L | repair: normalise GBp/GBX/ZAc/ILA → major unit using `history_metadata['currency']`. Check: day-over-day close ratio ≈100 or ≈0.01; dividend/price yield > 25% ⇒ suspect |
| Reporting currency ≠ trading currency; Yahoo's own P/B etc. mix them | yfinance #1976 (maintainer: use `financialCurrency`), PR #2632 (open) | principle 2: two currencies per instrument + fx conversion in calc helpers |
| Price history errors: missing split/dividend adjustment, bad ticks, missing days | yfinance price-repair docs; #2621, #2964 | fetch with `repair=True`; record the `Repaired?` column as a repair; check trading-day count against an exchange calendar; widen ranges when repairing |
| Statement columns misaligned / oldest period sparse | yfinance #2584 | check: drop period columns >70% NaN (recorded); check Assets ≈ Liabilities + Equity per period ⇒ suspect |
| Only ~4 annual / ~5 quarterly periods | yfinance #1747 (weak) | depth-aware coverage (see Known data limitations) |
| Empty statement frames (transient) | yfinance #2790/#2791 | classify as `error` (retry), not `empty` |
| Capex reported negative | convention, unverified | canonical schema fixes the sign (capex stored positive = cash spent); adapter maps it explicitly; contract test on a canary |
| Share counts: multi-class / dual-listed (`sharesOutstanding` vs `impliedSharesOutstanding`) | Yahoo AU feedback (weak) | check: price × shares vs reported market cap within tolerance ⇒ else suspect |
| `.info` staleness | yfinance #2042 (weak) | profile TTL; check `currentPrice` vs latest close |
| Screener omits sector | alpha-capture `universe/AGENTS.md` | sector from `profile` dataset (cached), joined before stratification |
| No scale flag for thousands/millions | none found, either in alpha-capture history or yfinance issues | check anyway: statements net income vs `.info` net income; ratio ≈1e3/1e6 ⇒ rejected |

alpha-capture bugs **not** to port (the logic behind them): a truthiness check turning
a real 0 into "missing"; `date.today()` as a fallback period date; a positional concat
when `period_ending` is missing; first-writer-wins alias collisions.

### Provider fallback (Claude's call)

- Fallback is **per entity per dataset**. The primary provider is tried. If it reports the
  entity unsupported or `empty` (e.g. EDGAR for a non-US ticker), the next one is tried.
- There is no per-field or per-period mixing within one entity's dataset slice, so
  `pit_reliable` is unambiguous per slice.
- Ticker→CIK uses SEC's published ticker map. The XBRL-tag→canonical-line-item mapping
  is left to the builder (start with a curated map for the line items the v1 calcs need).

### Prices and point-in-time (Claude's call)

- `known_at` for a price row = that trading date's close. A price is public when it prints,
  so historical backfills are point-in-time for as-of purposes.
- Store the provider's close, dividends and split ratio. **No adjusted close**: Yahoo's
  adjusted close rewrites the past on every dividend, which breaks append-only facts. The
  total-return adjustment is our own calc node (M5). Returns, trend ratios, volatility and
  drawdown over windows ending at `as_of` use split-adjusted closes and are unaffected by
  later splits. The v1 price lens is ratio-based, so as-of runs are clean.
- `profile` stores shares outstanding, not market cap; market cap = price × shares is
  computed (data quality principle 1).
- Calcs that use price *levels* (absolute price filters, market cap = price × shares) must
  declare `level_based = True`. In as-of runs they warn: yfinance's "close" is already
  split-adjusted.
- `prices` is therefore `pit_reliable = true` for ratio-based use.

### Currency (Claude's call)

- Providers normalise units (e.g. GBp → GBP).
- Absolute thresholds (market cap, traded value) are expressed in **USD**, using an `fx`
  dataset (daily FX rates from yfinance) converted point-in-time.
  USD is kept as the base currency (user, 2026-11-25) even with a UK + Europe focus.
- Cross-region campaigns (UK + several European currencies) need comparable thresholds;
  local-currency thresholds would make "balanced" meaningless.

### Known data limitations (documented, not solved in v1)

- **UK/European fundamentals have no free point-in-time source wired in** equivalent to
  EDGAR, and yfinance typically returns only ~4 annual periods (`pit_reliable=false`).
  - Lead for M6 (*unverified*): listed UK/EU companies file ESEF iXBRL annual reports;
    filings.xbrl.org may provide them with filing dates for free, i.e. a possible
    point-in-time provider for this region.
  - **Decision (user):** run on what's available. `quality_value` declares
    `desired_periods=8, min_periods=3` on fundamentals. Thin history lowers coverage, and
    so the lens's weight and the dossier's confidence (see core.md, aggregation).
  - A paid deep-history provider can be added later as one adapter.
  - Fundamentals-based *backtests* are US-only. Price-based backtests work for all regions.
- **Survivorship bias**: `screen` lists only currently trading securities. As-of
  universes are biased until a delisted-securities source is added (typically paid).
- yfinance news covers only recent items. News-dependent lenses can't be backtested (they're AI anyway).

## v1 lenses

All three share calc nodes where they overlap. No lens reads another lens's verdict.

### 1. `price_behaviour` (deterministic)

Components (each a calc node output, scored and weighted; weights and thresholds are params):

| Component | Calc | Direction |
|---|---|---|
| momentum | 12-1 month total return (12m excluding most recent month) | higher is better |
| trend | price vs 200-day moving average (% above/below), plus slope | above/rising is better |
| risk | realised volatility (e.g. 1y daily, annualised) and max drawdown (e.g. 3y) | penalty |

Claims are templated per component and cite calc fields. This is the lens used for
as-of backtests first.

Default thresholds and weights are left to the builder. They are absolute (no
cross-candidate ranking in v1) and exposed as params. The backtest is how they get calibrated.

### Lens backtests (Claude's call; milestone 8)

- This is a separate **evaluation module** outside the lens graph. Forward returns
  necessarily use post-`as_of` data, which no run may see.
- Procedure: run the panel (deterministic lenses only) at monthly `as_of` dates over N
  years, for a fixed universe (survivorship-biased, documented). Then compute forward
  returns (1m / 3m / 12m, vs. a benchmark index) from the source store.
- Metrics: rank IC of score vs. forward return, mean forward return by stance bucket, hit
  rate. A small HTML report.
- Not in scope: transaction costs, portfolio simulation.

### 2. `quality_value` (AI)

- **Calc inputs** (deterministic, citable fields):
  - ROE (level and consistency over ~5–10y)
  - operating margin level and stability
  - debt/equity and interest cover
  - owner earnings (net income + D&A − maintenance capex proxy)
  - FCF conversion
  - share-count trend
  - earnings consistency (no losses / volatility)
  - a valuation range: owner-earnings yield vs. a hurdle, plus a simple intrinsic-value band
- **Text inputs**: profile business summary; 10-K business section where available (US); recent news.
- **Default prompt**: a rubric that states Buffett's principles faithfully, grounded in
  primary sources.
  - Berkshire's published acquisition criteria (consistent earning power; good returns on
    equity with little or no debt; management in place; simple, understandable businesses;
    a sensible price).
  - The shareholder letters' concepts: durable competitive advantage ("moat"), circle of
    competence, owner earnings, margin of safety.
  - The rubric file lists each principle with its source (letter/year), so it can be
    checked. It sits at the start of the prompt for prompt caching.
- **Variant `buffett_persona`**: "assess as Warren Buffett would", plus instructions not
  to caricature and not to use knowledge of his actual holdings or comments about this
  company. It's there to compare against the rubric (stance agreement, citation patterns).
  It is not the default.
- The LLM judges moat/management/understandability from text and interprets the calc
  numbers. It never computes them.

### 3. `price_vs_fundamentals` (AI, hybrid)

- Framed as a **divergence check**, so momentum isn't double-counted: does the price action
  agree with the fundamental trend?
- **Calc inputs**:
  - the momentum and trend calcs (shared with lens 1)
  - fundamental trend calcs: revenue growth, margin change, EPS growth, FCF trend
    over recent periods (shared with lens 2 where they overlap)
  - valuation change (e.g. P/E or EV/EBIT now vs. 1y ago)
- **Output**: stance on whether fundamentals support the price. Flags such as
  `price_up_fundamentals_down` (warn) and `derating_despite_improvement` (info).

### Optional later lens: `investability` (deterministic)

Liquidity, market cap, listing age, data coverage. It is likely to be more useful as a
campaign stage-0 gate than as a lens.

## Universe campaign (finance instantiation of core campaigns)

Example (user's motivating case): equities listed in the UK and Europe, balanced
across sectors, at least 50 accepted, with a cap on candidates evaluated.

```yaml
campaign:
  population: {source: yfinance_screen, regions: [gb, de, fr, nl, ch, se], min_mcap: 300e6, min_volume: 50e3}
  strata: sector
  quotas: {total_min: 50, mode: equal}          # per-sector min derived from total and strata count
  stages:
    - targets: [screen_filters]                 # stage 0: metadata only, no fetches beyond screen
    - targets: [price_behaviour]                # stage 1: prices only
      gate: {reject_if: "stance <= -1 or status == 'failed'"}
    - targets: [quality_value, price_vs_fundamentals]
  acceptance: {policy: overall_stance_floor, floor: 0.5, reject_on_flags: [veto]}
  budget: {max_evaluated: 400, max_llm_cost_usd: 20}
  batch_size: 20
  seed: 7
```

Requirements carried over from alpha-capture's failures:
- The population is the **full screened set** (paginated), not the top-N by volume.
  Liquidity is a filter, not an accidental bias.
- Strata attributes come from `profile` through the source store (cached, TTL'd). Sector
  filtering happens *after* sector is known. alpha-capture's sector filter was a no-op
  because enrichment happened later.
- Exhausting a stratum is reported, never papered over.

Gate expressions above are illustrative. Policies are registered Python callables with
params. A string expression language is not required.
