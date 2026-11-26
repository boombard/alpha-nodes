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
| `fundamentals` | none (snapshot, keyed by period and filing) | annual income/balance/cash-flow line items with `period_end`, `filed_at` where available (M6: annual only; see Fundamentals below) |
| `news` | none (snapshot, keyed by item id) | id, published_at, headline, source, url, summary. Providers may only serve recent items; stored items accumulate across fetches |
| `filings_text` | filing date | e.g. 10-K "Business" + "Risk factors" sections (US). **Deferred** (M6 plan): US-only and fragile HTML section extraction; the profile business summary covers every region |
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
- **Exceptions** (the store is append-only and never refetches a covered range, so a
  response that is probably a glitch is `error`, never `ok`):
  `YFRateLimitError`, HTTP 401/403 and any message containing "Invalid Crumb" or
  "Unauthorized" → `rate_limited` (an auth failure is provider-wide). `YFTzMissingError`
  → unknown ticker → `empty`. `YFPricesMissingError` is raised both for unknown tickers
  and for a valid ticker with no bars in the range: `empty` when no timezone is known;
  with a known timezone, `ok` with an empty payload only if the exchange calendar has no
  session in the interval (weekend, holiday), else `error` ("no bars for a range with N
  sessions"). Accepted cost: a delisted ticker topped up past its last bar raises
  `SourceUnavailable` every run (delisting is M7/M8 work). HTTP 404 is `empty` only for a
  symbol with no known timezone (first sight), `error` for a known one. An unknown
  exchange suffix is `empty`, never raised. A 404 may cost 2–3 requests (crumb refresh;
  *unverified*).
- **Settled tail**: when the requested interval reaches into the last 3 settled sessions
  and the payload lacks bars for some of them at its end, `settled_through` is capped at
  the last bar date, so the missing tail stays a gap and is asked again next run. A last
  bar older than those 3 sessions (suspended, delisted) does not cap. Fx applies the same
  rule to weekdays (fx does not trade at weekends, and its settled date, the previous UTC
  day, can land on one); a weekend-only fx range with no bars is an `ok` empty interval.
- **Truncated history**: if the first bar is more than 5 sessions after the first session
  on or after `max(request start, metadata firstTradeDate)`, the outcome is `error`
  ("history truncated"), since Yahoo sometimes answers a long request with only its
  recent part. Prices only.
- **Settled cut-off**: Yahoo returns a live bar for today while the market is open.
  Settled = last trading day before today in the exchange's timezone, or today once
  the exchange's close + 30 min has passed.
- **Top-ups and repair**: a short top-up window gives `repair=True` little context. When a
  top-up shows a new split/dividend, refetch a wider window (3–6 months) for that ticker.
- **Starting rate-limit policy** (Yahoo publishes no limits; tune from the attempt log):
  concurrency 4, ~2 requests/s with burst 4, provider-wide pause on rate limit with
  backoff 30/60/120/240 s + jitter, `GlobalFailure` after 3 consecutive rate-limit
  episodes, 5 consecutive connection failures, 5 consecutive `error` outcomes
  (`max_consecutive_errors`) or 20 consecutive `empty` outcomes (`max_consecutive_empty`)
  across distinct entities; `yf.config.network.retries = 2`,
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
- (TASK-32, canary run 2026-11-25) `.info` has no `firstTradeDateEpochUtc`; the first trade
  date is `firstTradeDateMilliseconds`. `Ticker.isin` is `"-"` for most non-US symbols and
  was wrong for ASML.AS (an `AR...` ISIN), so the profile ISIN is a hint, never a join key.
  `financialCurrency` differs from the trading currency for BP.L, HSBA.L (USD), VOD.L (EUR)
  and ALCLS.PA (USD). An ETF (VUSD.L) has no `sharesOutstanding`, so it is `suspect`.
- **Request counts** (canary, live): a history fetch costs 3-5 HTTP requests on a symbol's
  first sight and 1-2 once caches are warm; `repair=True` adds 2 requests for GBp symbols
  (3 vs 1) and none for AAPL. A profile (`.info` + `.isin`) costs 3-4 first sight and 2 warm.
  The limiter's one-request-per-item assumption undercounts; TASK-37 should weight it.
- Four concurrent workers over 11 symbols (prices and profile), both with freshly relocated
  tz/cookie cache files (cold) and warm, raised no "database is locked", crumb or rate-limit
  errors. A brand-new process's very first concurrent request is not covered.
- Yahoo answers `.info` for an unknown symbol with a non-empty stub dict; no `currency` in
  `.info` is therefore classified `empty`. Illiquid LSE names (Braime Group, BMT.L: 213 of 506
  bars at zero volume) keep a bar for every session with the close carried forward, so
  missing sessions is not the no-trade signal there; zero volume is.

### Data quality: yfinance quirks and how we handle them

Researched 2026-11-23: the old repo's fixtures and code, plus yfinance issues and changelog.
Five principles:

1. **Don't ingest Yahoo's derived ratios.** `.info` ratios (debt/equity, dividendYield,
   P/E, P/B, margins) are where most unit and currency bugs live. Ingest raw ingredients
   instead: statement line items, prices, dividends, share counts. Compute every ratio in
   our own calc nodes. This is the guard-rail principle applied to data.
2. **Units and currency are data, not convention.**
   - Each numeric canonical field declares its unit (core.md, Units): money and per-share money
     (prefixed from the row's currency column), shares, a fraction for ratios, count. Every
     numeric result field declares one too. The units live in `alpha_nodes.units`; they replace
     the earlier `metadata={"kind": ...}` tags (TASK-69).
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
| Statement columns misaligned / oldest period sparse | yfinance #2584 | check: period columns >70% NaN in any statement become `rejected` rows (`sparse_period`, recorded, hidden from default reads); check Assets ≈ Liabilities + Equity per period ⇒ suspect |
| Only ~4 annual / ~5 quarterly periods | yfinance #1747; *confirmed 2026-11-26*: every canary statement has 5 yearly columns (BP.L's balance sheet 4), the oldest 85-98% NaN, so exactly 4 annual periods survive the 70% rule | depth-aware coverage (see Known data limitations) |
| Empty statement frames (transient) | yfinance #2790/#2791 | classify as `error` (retry), not `empty` |
| Capex reported negative | *verified 2026-11-26*: `Capital Expenditure` is negative on all nine canaries | canonical schema fixes the sign (capex stored positive = cash spent); adapter maps it explicitly; contract test on a canary |
| Share counts: multi-class / dual-listed (`sharesOutstanding` vs `impliedSharesOutstanding`) | Yahoo AU feedback (weak) | check: price × shares vs reported market cap within tolerance ⇒ else suspect |
| Duplicate bars (two bars on one local date) | yfinance chart quirk | collapse to one row per date: the last with a non-NaN close, carrying non-zero dividends/splits from any row; reason `duplicate_bar` |
| Single missing sessions | fixtures have none, even for illiquid BMT.L (Yahoo carries the close forward) | reason `missing_sessions:<n>` for n ≥ 1 (was ≥ 3) |
| Split not applied to closes (closes are already split-adjusted, so a correct split shows no jump) | yfinance price-repair docs | a close/previous close within 3% of 2, 3, 4, 5, 8, 10 or 20, or their inverses: `unadjusted_split` if that day has a split row, else `split_like_jump` |
| Dividend in pounds against pence prices (divided by 100) | GBp quirk above | 0 < dividend/close < 0.0002 ⇒ `dividend_yield_lt_0.02pct` |
| Stale prices: the same close repeated | Yahoo serving a frozen quote | a run of ≥ 5 sessions with an identical close **and missing (NaN) volume** ⇒ `stale` on each bar. Zero volume is not stale: illiquid names (BMT.L: runs of 9 identical zero-volume closes) are genuinely not trading |
| Fx jumps and frozen rates | rates move little day to day | close/previous > 1.10 or < 1/1.10 ⇒ `fx_jump`; ≥ 5 identical consecutive closes ⇒ `stale` |
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
- **EDGAR gaps by industry:** banks, insurers and REITs often lack `total_debt`, `capex` and `interest_expense` under
  the mapped tags, and banks, insurers and some pharma (JNJ, PFE) report no operating income line. These fields stay
  None; there is no derivation (revenue minus costs does not reconcile to pre-tax income), so operating margin and
  interest cover are None for them. Measured on 23 large filers (tests/fixtures/edgar/README.md): in the latest filing
  operating income is missing for 9, interest expense for 9, capex for 6, total debt for 1.
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

**Pinned conventions (Claude's call, M5 plan 2026-11-25).** The kernels named here are in
`alpha_nodes.kernels` (see Calculation layers).

- **Windows count bars (sessions), not calendar days:** 1 month = 21, 12 months = 252,
  3 years = 756. Annualisation uses 252 for every venue.
- **Total-return index** (`total_return_index`): `TR_0 = 1`,
  `TR_t = TR_{t-1} × (close_t + dividend_t) / close_{t-1}`, with the dividend on its ex-date
  row. `split_ratio` is **not** applied, because yfinance closes are already split-adjusted.
  Dividends are assumed to be on the same split basis as the closes. M5.3 checked what the
  AAPL fixtures show: closes are split-adjusted through the 4:1 split of 2020-08-31 (the TR
  index moves 3.4% that day, no 4× artefact), and the two-year AAPL fixture's eight payouts
  (0.25–0.27) form a smooth series whose trailing-year yield is a plausible AAPL 0.2–1.5% (a ×4 basis
  error would fall outside). The recorded split window contains no dividend, so a
  payout straddling a split is *not* directly observed; the assumption rests on yfinance
  adjusting both columns together.
- **Momentum 12-1** (`skip_return`): `TR[-1-21] / TR[-1-252] - 1`. It needs ≥ 253 bars, else
  None.
- **Trend:** MA = `sma(close, 200)` on split-adjusted closes (price, not TR, by convention).
  `pct_above_ma = close[-1] / MA[-1] - 1`. `ma_slope` = `linreg_slope(ln MA, 20)[-1] × 252`,
  the annualised log growth of the MA. It needs ≥ 219 bars, else None.
- **Realised volatility** (`realised_volatility`): std of daily log TR returns over the last
  252 returns, `ddof=1`, × √252. TA-Lib `STDDEV` is the population std (`ddof=0`), so its
  oracle test rescales by √(n/(n−1)). It needs ≥ 63 returns, else None.
- **Max drawdown** (`max_drawdown`): over the last ≤ 756 bars of TR,
  `min_t(TR_t / max_{s≤t} TR_s) − 1`, a non-positive fraction. It needs ≥ 252 bars, else
  None. The number of bars actually used is reported.
- **Data quality:** rows labelled `suspect` are used, and each metric reports how many
  were in its window (`suspect_bars`). Rows labelled `rejected` never reach calcs (the fetch
  node's default). The lens raises a `data_quality` warn flag when any window had suspect
  bars.
- Too little history means the field is None and its component is skipped. The lens's
  coverage does not drop yet; that is TASK-25 (critical inputs and minimum coverage).

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
- **Text inputs**: profile business summary; recent news. (A 10-K business section for US names waits for `filings_text`, deferred.)
- **Default prompt**: a rubric of seven principles stated neutrally and operationally, with
  no investor, company, letter, year or book names, so the model isn't primed to recall
  Buffett's holdings or views (several demo names are famous Berkshire holdings) and the
  comparison with the persona variant stays clean.
  - The principles: consistent earning power; good returns on equity with little or no
    debt; management in place; a simple, understandable business; a durable competitive
    advantage; owner earnings (proxy); a clear discount to a conservative value estimate.
  - Each principle's primary source (acquisition criteria, shareholder letters by year,
    Graham) is listed in the `QualityValue` class docstring, so it can be checked.
  - It sits at the start of the prompt for prompt caching.
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

### Fundamentals: datasets, providers and pinned conventions (Claude's call, M6 plan 2026-11-25)

**Dataset shapes.**
- `fundamentals` is **annual only** in M6 (`period_type == "annual"`). Quarterly periods need
  YTD de-accumulation on EDGAR (10-Qs report year-to-date; Q4 exists only as FY − 9M) and give
  yfinance ~5 periods; they wait for a later milestone.
- One **wide** row per (period, filing): canonical line items are typed columns with field
  kinds, in the reporting currency's major unit, with a `currency` column. Key columns
  `(period_type, period_end, filed_at)`; axis `none` (a snapshot refetched after the TTL, 7 days).
- One fetch of EDGAR company facts holds every filing, including the comparatives a later
  10-K re-reports. Each (period, filing) is its own key and `known_at = filed_at`, so as-of
  queries see exactly what was filed by then. The adapter `annual_periods` then keeps, per
  `period_end`, the latest filing known on the date asked about (restatements win once filed).
- yfinance has no filing dates: `filed_at` is null, `known_at` = first seen, `pit_reliable=false`.
  Periods Yahoo drops later stay in the store (facts are append-only), so a UK name's history
  slowly grows from the ~4 years Yahoo serves.
- `news` is a snapshot keyed by `id` with a 1-day TTL and `known_at = published_at`; items
  accumulate across fetches. Items are untrusted text: prompts present them as evidence to
  weigh, never as instructions.

**Canonical line items** (all nullable floats, kind `money` unless noted): `revenue`,
`operating_income`, `net_income` (attributable to common shareholders), `interest_expense`
(positive = cost), `depreciation_amortization`, `operating_cash_flow`, `capex` (positive =
cash spent), `total_assets`, `total_liabilities`, `total_equity` (incl. minority interest),
`common_equity` (attributable to the parent), `total_debt`, `cash`, `shares_diluted`
(weighted average, kind `shares`), `shares_outstanding` (period end, kind `shares`).
EPS is computed (`net_income / shares_diluted`), never ingested (data quality principle 1).

**Providers.**
- `EdgarProvider` (`edgar`): SEC company facts (`data.sec.gov/api/xbrl/companyfacts`), US
  `us-gaap` 10-K filers only. Entities are Yahoo symbols; a symbol with an exchange suffix
  is `empty` without a request, and so is a ticker missing from SEC's ticker map (cached in the
  provider cache dir, 7 days). Annual facts: form 10-K or 10-K/A, `fp == "FY"`, and for flow
  items a duration of 350–380 days. A curated map gives each canonical item ordered *synonym* `us-gaap` tags (the same quantity under
  other names or eras) and *fallback* tags (a different scope); per (period, filing) the first synonym with a value is
  used, and when a later synonym also has a value that differs by more than 1%, the row is `suspect`
  (`tag_conflict:<item>`). Never first-writer-wins silently. User-Agent from
  `ALPHA_NODES_SEC_USER_AGENT` (never committed); the factory fails clearly when it is unset.
  Rate limit: SEC allows 10 requests/s; declare concurrency 2, 5/s. **The empty breaker is off**
  (`max_consecutive_empty=None`): a UK/European universe is all `empty` for EDGAR by design.
  `pit_reliable=true`.
  *Verified 2026-11-26 on recorded AAPL, KO and LAKE facts (tests/fixtures/edgar/README.md):* the design holds
  (each 10-K re-reports two to three prior years, so most periods have several filings). Corrections: a 10-K also
  carries ~90-day `fp == "FY"` quarter facts and off-period instants, so a period exists only where some flow item
  has a full-year fact; revenue tags change over time (`SalesRevenueNet`/`SalesRevenueGoodsNet` before 2016-18,
  then `Revenues` or the ASC 606 tag), and some filers never tag `Liabilities` or `CommonStockSharesOutstanding` (KO): `total_liabilities` is then
  `LiabilitiesAndStockholdersEquity - total_equity` when `total_equity` is the NCI-inclusive tag (`derived:total_liabilities`),
  else null, and `shares_outstanding` is `CommonStockSharesIssued` minus treasury shares, else the same filing's single
  `dei` cover-page count (`fallback:shares_outstanding=dei_cover`); several cover counts (share classes) leave it null
  with reason `multi_class:shares_outstanding` on an otherwise `ok` row. Different tags in one filing are usually different
  measures, so each item's tags are split into *synonyms* (conflict-checked as above) and *fallbacks* (a different scope,
  used only when no synonym has a value, never compared, recorded in `repairs` as `fallback:<item>=<tag>`). `total_debt` is composed, not
  first-tag-wins: `LongTermDebt` (incl. current maturities; else `LongTermDebtNoncurrent` + `LongTermDebtCurrent`; Noncurrent
  alone marks the row `suspect`, `partial:total_debt`; else the non-current `LongTermDebtAndCapitalLeaseObligations` + its
  current tag, or alone as `partial:total_debt`, or its `...IncludingCurrentMaturities` twin) plus short-term borrowings
  (`ShortTermBorrowings`, else `CommercialPaper`, else 0); as a last resort the all-in `DebtAndCapitalLeaseObligations`
  alone. When a non-current long-term figure is used and `DebtCurrent` (all current debt) is tagged, `DebtCurrent` is its current
  part and nothing else is added; a complete composition always beats a partial one. Each non-plain path is recorded in `repairs`. This matches Yahoo's "Total Debt"; finance leases are included on the
  capital-lease paths, operating lease liabilities are excluded. Revenue: `Revenues` (total, incl. leasing and finance income)
  and `SalesRevenueNet` are synonyms; the narrower ASC 606 contract-revenue tags are fallbacks. A company-facts 404 is `empty`.
  The ticker map is cached with its fetch time inside `company_tickers.json` in the provider cache dir.
  10-K text (`filings_text`) is deferred.
- `YFinanceProvider` adds `fundamentals` (annual income statement, balance sheet and cash
  flow merged on `period_end`, plus `financialCurrency` and `.info` net income for the scale
  check) and `news`. An empty statement set is a transient `error`; an unknown symbol `empty`.
  Period columns more than 70% NaN become `rejected` `sparse_period` rows (finance quirk table);
  capex is mapped to positive (`capex_sign` repair). `pit_reliable=false` for both.
  *Verified 2026-11-26 on nine recorded canaries (tests/fixtures/yfinance/README.md):* the statements carry no
  currency, so the reporting currency is `.info` `financialCurrency` (present on all nine; none a minor unit);
  a period that is sparse in any one statement is rejected (`sparse_period`) for all three, kept as a mostly-NaN row, not dropped; HSBA.L (a bank) has
  no operating income row (null, not 0); `.info` `netIncomeToCommon` is trailing-twelve-month, so the scale check
  only trips near 1e3/1e6, never on the tens-of-percent TTM gap. Rows rejected for a missing currency (`no_currency`) or an unrecognised
  code (`unknown_currency:<code>`) carry a null `currency` (nullable in the schema for exactly these rows; no guess). The fetch reads
  `.info` first: no `currency` there is an unknown symbol (`empty`), and only then are all three empty statements
  a transient `error`. News: `get_news(count=20)` returns nested `content` items (title, `pubDate`, provider,
  click-through URL, summary); `[]` is `ok` with no items.
- Run configs use `providers: {fundamentals: [edgar, yfinance]}`: US names come from EDGAR,
  the rest fall back to yfinance (per entity, core.md Source store).

**Checks on `fundamentals` rows.** `suspect` when `total_assets` and `total_liabilities +
total_equity` differ by more than 2% (`balance_mismatch`); `rejected` when statements net
income and `.info` net income differ by a factor near 1e3 or 1e6 (`scale_mismatch`); `rejected`
with no reporting currency (`no_currency`). `tag_conflict` as above.

**Pinned conventions.** Kernels in `alpha_nodes.kernels.fundamentals`; adapters in
`alpha_nodes.statements`.
- **Known on a date:** a period counts as known on day `d` if `filed_at <= d`, or, when
  `filed_at` is null, if `period_end + FILING_LAG_DAYS (90) <= d`. Calcs use `as_of`, else the
  run's today. Windows take the last ≤ `MAX_ANNUAL_PERIODS` (10) known periods.
- **ROE** = `net_income / common_equity` per period (None when equity ≤ 0). Reported:
  mean, min, and std (`ddof=1`, needs ≥ 3 periods).
- **Operating margin** = `operating_income / revenue` (None when revenue ≤ 0); mean and std.
- **Latest-point fields and older-period fallback.** "Latest" for leverage, coverage, net
  debt, owner earnings and FCF means the newest of the last `MAX_STALE_PERIODS + 1` (3) periods
  that hold *all* of that field's inputs (`statements.latest_complete`), one row per field, so a
  ratio never mixes periods. Past the cap the field is None. A field taken from an older period
  is recorded in the result's `field_periods` (field name → its `period_end`), listing only
  fields older than the reported `last_period_end`. The window of `balance_sheet` spans from the
  oldest row used to the latest period; so does the `cash_generation` window (the oldest row any
  of its fields used, including FCF conversion and share count).
- **Leverage** (latest point, see above): `debt_to_equity = total_debt / common_equity` (None
  when equity ≤ 0); `interest_cover = operating_income / interest_expense` (None when interest
  expense is missing or ≤ 0); `net_debt = total_debt − cash`.
- **Owner earnings** (latest point, see above) = `net_income + depreciation_amortization − min(capex,
  depreciation_amortization)`: maintenance capex is proxied by D&A, capped at actual capex.
- **FCF** (latest point, see above) = `operating_cash_flow − capex`; **FCF conversion** = Σ FCF / Σ net income over the
  window (None when Σ net income ≤ 0).
- **Share-count trend** = CAGR of `shares_diluted` from the first to the last period of the
  window, in years between their `period_end`s (needs ≥ 2 periods).
- **Earnings consistency:** `loss_years` = periods with net income < 0;
  `net_income_cv` = std / mean (None when mean ≤ 0 or fewer than 3 periods).
- **Growth** (`growth(prev, cur)`) = `(cur − prev) / |prev|`, None when `prev == 0`; CAGR needs
  both ends > 0. `revenue_growth_1y`, `revenue_cagr_3y`, `eps_growth_1y`,
  `fcf_growth_1y`; `op_margin_change_1y` is the difference in margin (fraction points).
  Spans are measured on `period_end` dates (`years_between` = days / 365.25, also used by the
  share-count CAGR). The "1y" fields compare the latest two periods and are None when their
  `period_end`s are more than 18 months apart. The `revenue_cagr_3y` base is the period whose
  `period_end` is closest to three years before the latest, within 6 months (else None), and
  it compounds over the actual span.
- **Market cap** = close on the day × `shares_outstanding` of the latest known period, in the
  trading currency, converted to the reporting currency through `fx` on that day
  (`alpha_nodes.money`; mixing currencies without fx raises `CurrencyMismatch`). It is
  level-based (see Prices and point-in-time).
- **Valuation** (latest known period): `owner_earnings_yield` = owner earnings / market cap;
  intrinsic-value band = owner earnings capitalised at the hurdle rates (default 12% → low,
  8% → high; None when owner earnings ≤ 0); `price_to_value` = market cap / band midpoint. Earnings yield and P/E use
  net income / market cap; P/E is None when earnings ≤ 0.
- **Valuation change:** the same at `as_of` and 252 bars earlier, each with the periods known
  on its own day; `pe_change = pe_now / pe_then − 1`.
- Every fundamentals result reports its window (`periods`, first and last `period_end`,
  `suspect_periods`, `currency`); a field that can't be computed is None, never 0.

**Lens inputs and abstention.** Both AI lenses take the `annual_fundamentals` frame as a
critical input with a depth requirement (`quality_value`: desired 8, minimum 3;
`price_vs_fundamentals`: desired 4, minimum 2), so a name with too few periods abstains before
any LLM call (TASK-25). The lenses also see each result's `field_periods` as a caveat: a field
listed there comes from an older period than `last_period_end`, and the prompts tell the lens to
weigh it accordingly and lower its conviction when key fields are stale (the lens judges; nothing
is down-weighted deterministically). Neither lens sees analyst ratings or price targets (LLM herding risk).

### Optional later lens: `investability` (deterministic)

Liquidity, market cap, listing age, data coverage. It is likely to be more useful as a
campaign stage-0 gate than as a lens.

## Calculation layers (user, 2026-11-25)

Financial maths is written as **small, atomic numpy functions with their own tests**, and
then applied to pandas frames. There are three layers, each depending only on the one below:

1. **Kernels** (`alpha_nodes.kernels`, modules by topic: `returns`, `rolling`, `risk`, …):
   - Pure functions on 1-D `float64` numpy arrays. Params are plain ints and floats.
   - No pandas, dates, I/O, quality labels or pydantic.
   - **NaN policy:** non-finite input raises `ValueError`; gaps are handled above, never
     silently inside a kernel. Rolling kernels return an array of the input's length with
     a leading-NaN warm-up (TA-Lib's lookback convention). Scalar kernels return `nan` when
     the input is shorter than they need.
   - Each kernel has its own unit tests: hand-computed values on tiny arrays, edge cases
     (too short, constant, a single bar, non-finite input), and a TA-Lib oracle test where
     an equivalent exists.
   - A kernel's docstring states its formula and conventions (ddof, window, annualisation).
2. **Frame adapters** (`alpha_nodes.series`): thin pandas glue. They take canonical frames
   (e.g. `PriceSchema`), check date order and uniqueness, choose trailing windows in bars,
   call kernels on `.to_numpy()`, and return date-indexed Series, or scalars plus window
   facts (bars used, dates, suspect bars). They hold no maths of their own.
3. **Calc nodes** (`alpha_nodes.nodes`): `CalcNode`/`TransformNode` subclasses. They expose
   windows as params, call adapters, and return pydantic result models whose fields are
   what lenses cite. They declare the kernels and adapters they use in `code_deps`
   (core.md, Memoization); the price calc nodes are not memoized (below), so this only
   matters if caching is turned back on.

The bar-count conventions (`BARS_PER_MONTH`, `BARS_PER_YEAR`) live in
`alpha_nodes.conventions`. Calc nodes are **not memoized**: they cost milliseconds and their
outputs are stored for lineage anyway, so caching saves almost nothing, and it risks stale
results from things outside the memo key (module constants, library upgrades) that would
persist indefinitely in fixed as-of runs. Lenses, AI nodes and the reviewer stay memoized.

Lenses never call kernels or adapters directly. They read calc node outputs only.

## Technical analysis and TA-Lib (user, 2026-11-25)

The v1 price calcs are an MVP. Much more technical analysis is expected later.
[TA-Lib](https://github.com/TA-Lib/ta-lib) (C library, BSD-3) and its Python wrapper
[ta-lib-python](https://github.com/TA-Lib/ta-lib-python) are the reference implementations
for named technical indicators. They're used in two ways:

1. **Test oracle.** Our calcs are our own code (numpy kernels, see Calculation layers), with
   conventions pinned in this doc. Where a kernel has a TA-Lib equivalent, its tests also
   compare it against TA-Lib
   on the same series (e.g. `SMA`, `LINEARREG_SLOPE`, `STDDEV` with the ddof difference
   made explicit). TA-Lib is a **dev dependency** only, until a production calc needs it.
   - Calcs TA-Lib doesn't cover (12-1 total-return momentum, max drawdown, total-return
     adjustment, all fundamentals) are tested against hand-computed values only.
2. **Research reference.** A local snapshot of TA-Lib's per-function docs (formula,
   inputs, params, defaults, notes) lives in `documentation/reference/ta-lib/`, with an
   index. Agents read it when choosing or specifying indicators. It records which
   functions the pinned ta-lib-python version actually exposes, because the docs on
   TA-Lib's `main` can run ahead of the released wrapper.

When a production calc is a convention-heavy indicator (Wilder smoothing in RSI/ATR/ADX,
MACD, stochastics, candlestick patterns), calling TA-Lib directly is an option. It goes
behind a kernel in `alpha_nodes.kernels` (same signature and tests as any kernel), never in lenses, the same way providers sit behind
adapters. Watch for TA-Lib's NaN behaviour: a gap can turn the rest of a smoothed output
into NaN, so inputs need explicit gap handling.

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
