# yfinance recorded fixtures

Recorded live on **2026-11-25** with **yfinance 1.8.0** (curl_cffi transport) by
`packages/alpha_nodes/scripts/record_yfinance_fixtures.py`. Never hand-edit; re-run the script
and re-commit to refresh. Tests read these files and never touch the network.

Each `prices_*`, `fx_*` and `split_*` file is a `YFHistoryPayload` (see
`alpha_nodes/providers/yfinance/history.py`): `auto_adjust=False, actions=True, repair=True`,
requested interval ending 2026-11-24.

| File | Symbol | Requested range |
|---|---|---|
| `prices_BP.L.json` (GBp), `prices_HSBA.L.json`, `prices_VOD.L.json` | LSE | 2024-11-25 .. 2026-11-24 |
| `prices_ASML.AS.json` (EUR), `prices_SAP.DE.json` (EUR) | AMS, XETRA | same |
| `prices_NESN.SW.json` (CHF), `prices_NOVO-B.CO.json` (DKK) | SIX, CPH | same |
| `prices_AAPL.json` (USD) | NASDAQ | same |
| `fx_GBPUSD=X.json`, `fx_EURUSD=X.json`, `fx_CHFUSD=X.json`, `fx_DKKUSD=X.json` | FX | 2025-11-25 .. 2026-11-24 |
| `split_AAPL.json` | AAPL | 2020-08-28 .. 2020-09-03, contains the 4:1 split of 2020-08-31 |

All symbols succeeded.

## Exception probes

These record the exception yfinance raised (`exception`, `message`), not a payload:

- `probe_tz_missing.json`: `YFTzMissingError` for the unknown symbol `NOSUCH.XX`.
- `probe_prices_missing.json`: `YFPricesMissingError` for AAPL over a weekend (2026-01-03..04).
- `probe_http_404.json`: `HTTPError: HTTP Error 404` for the same unknown symbol on first sight.

## Findings (the design marked these *unverified*)

- An unknown symbol answers a bare HTTP 404 (curl_cffi `HTTPError`, `response.status_code ==
  404`) on its first one or two lookups, and `YFTzMissingError` only after yfinance has
  cached the missing timezone (third call in the recorder). The provider classifies the 404
  as `empty` directly, so it does not depend on yfinance's tz-cache internals or on retries.
- `yf.set_cache_location` does not exist at top level in 1.8.0; it is
  `yfinance.cache.set_cache_location`.
- `HAS_CURL_CFFI` lives in `yfinance._http`.
- LSE closes come back in pence (`currency == "GBp"`); `Repaired?` column is present on every
  frame, and `Adj Close` is returned and ignored.
- Fetch timeout is the `timeout=` argument of `Ticker.history`; `yf.config.network` has only
  `proxy` and `retries`.

## TASK-32 additions: profiles and three more canaries

Recorded the same day (2026-11-25, yfinance 1.8.0) with `record_yfinance_fixtures.py`. The
recorder now records only fixtures missing on disk; `--only NAME ...` re-records exactly the
named stems, so the TASK-31 price/fx fixtures were not touched.

`profile_<symbol>.json` is a `YFProfilePayload` (`Ticker.info` + `Ticker.isin`) for every
canary below. `prices_<symbol>.json` (2 years, ending 2026-11-24) exists for each too.

| Canary | Why | Trading / reporting currency (from the recorded payload) |
|---|---|---|
| BP.L, HSBA.L, VOD.L | LSE blue chips | GBp / USD, GBp / USD, GBp / EUR |
| ASML.AS, SAP.DE | EUR listings | EUR / EUR |
| NESN.SW, NOVO-B.CO | CHF, DKK | CHF / CHF, DKK / DKK |
| AAPL | US | USD / USD |
| **VUSD.L** | the `.L` line quoted in USD (Vanguard S&P 500 UCITS ETF) | USD / none; an ETF: no shares or business summary, so `no_shares` suspect |
| **BOOT.L** | UK small-cap (Henry Boot, ~GBP 0.2bn) | GBp / GBP |
| **ALCLS.PA** | European small-cap (Cellectis, ~EUR 0.1bn) | EUR / USD |

### Prices fixture statistics (computed by the recorder, `price_stats`)

Missing sessions are exchange sessions (per `alpha_nodes.markets`) between the first and last
bar with no bar; zero-volume are bars with `Volume == 0`; non-session are bars on a closed day.

| Fixture | bars | missing sessions | zero-volume | duplicate dates | non-session |
|---|---|---|---|---|---|
| `prices_AAPL.json` | 501 | 0 | 0 | 0 | 0 |
| `prices_ALCLS.PA.json` | 510 | 0 | 0 | 0 | 0 |
| `prices_ASML.AS.json` | 510 | 0 | 0 | 0 | 0 |
| `prices_BMT.L.json` | 506 | 0 | **213** | 0 | 0 |
| `prices_BOOT.L.json` | 506 | 0 | 0 | 0 | 0 |
| `prices_BP.L.json` | 506 | 0 | 0 | 0 | 0 |
| `prices_HSBA.L.json` | 506 | 0 | 0 | 0 | 0 |
| `prices_NESN.SW.json` | 499 | 0 | 0 | 0 | 0 |
| `prices_NOVO-B.CO.json` | 498 | 0 | 0 | 0 | 0 |
| `prices_SAP.DE.json` | 506 | 0 | 0 | 0 | 0 |
| `prices_VOD.L.json` | 506 | 0 | 0 | 0 | 0 |
| `prices_VUSD.L.json` | 506 | 0 | 0 | 0 | 0 |

The canary small-caps (BOOT.L, ALCLS.PA) are liquid enough to show nothing. `prices_BMT.L.json`
(Braime Group PLC, an AIM micro-cap; not a canary, prices only, chosen from a probe of 16
AIM names) is the illiquid evidence TASK-37 needed: **213 of 506 bars have `Volume == 0`
(42%)**, yet there are **no missing sessions**: Yahoo emits a bar for every session and
carries the last close forward on no-trade days (the close changed on only 3 of the 213
zero-volume days). So for illiquid LSE names a gap threshold on missing sessions never fires;
zero volume is the no-trade signal. (SAL.L had 120 and ARC.L 13; the other probed names 0-12.)

### Profile findings

- `.info` has **no `firstTradeDateEpochUtc`** in 1.8.0; the first trade date is
  `firstTradeDateMilliseconds` (epoch ms). `normalise_profile` uses it (and falls back to
  the epoch-seconds name if it ever appears).
- `Ticker.isin` is `"-"` for 9 of 11 canaries. Only AAPL (`US0378331005`) is correct.
  **ASML.AS returned `AR0725224551`, an Argentine ISIN, which is wrong** (ASML is NL...).
  Yahoo's ISIN lookup is a name search, so it is unreliable for non-US listings; treat the
  profile `isin` as a hint, not as a join key. (`test_dual_listing_has_isin` therefore uses
  AAPL, the only well-formed one.)
- `financialCurrency` differs from the trading currency for BP.L, HSBA.L (USD), VOD.L (EUR)
  and ALCLS.PA (USD), as the design predicted.
- Yahoo answers `.info` for an unknown symbol with a non-empty stub (e.g.
  `{"trailingPegRatio": None}`), not `{}`; the provider classifies info without a `currency`
  as `empty`, so `normalise_profile` never sees it (its `ValueError` is a backstop).
- ISINs are checked for shape and ISO 6166 check digit; a failure becomes None with `bad_isin`.
  This does not catch a well-formed wrong one (ASML.AS above).
- A profile fetch is `.info` (2 requests) plus `.isin` (1-2 more): 3-4 HTTP requests first
  sight, 2 once cookie/crumb and caches are warm.

## Live canary results (`scripts/canary.py`, 2026-11-25, `--concurrency 4`)

All 11 symbols ok; exit 0; health check ok. Run three times (after the repair-probe fix and again after adding the cold pass); the
counts were identical.

- **Request counting hook**: `curl_cffi.requests.Session.request` is patched at class level.
  yfinance's shared session (`yfinance.data.YfData()._session`) is a `curl_cffi` `Session`
  whose `get` and `post` both call `self.request`, and patching the class survives yfinance
  replacing the session (cookie strategy fallback). Labels are thread-local.
- **Requests per `history()` (provider fetch, 2-year-padded window)**: first sight of a symbol
  **3-5** (usually 4: cookie, crumb, tz lookup, chart; AAPL 2, as its cookie/crumb were
  already warm from the health check); cached **1-2** (chart, plus 1 more for the GBp
  repair on `.L`, and the provider's own `history_metadata` access). The limiter's
  one-request-per-item assumption therefore undercounts by about 2x warm and 4-5x on the
  first symbol.
- **`repair=True` extra downloads**: yes, for GBp symbols. BP.L and HSBA.L: 3 requests with
  `repair=True` vs 1 with `repair=False` (warm). AAPL: 1 vs 1. A repeated identical request is
  answered by yfinance's own cache with 0 requests, so the probe uses a different window per
  call.
- **Concurrency 4** (thread pool, 11 symbols x prices and profile), run twice, **cold** then
  **warm**: no errors in either, no SQLite "database is locked", no crumb errors, no rate
  limiting. "Cold" means a fresh provider, which moves yfinance's tz and cookie cache files to
  an empty directory, so all 11 symbols' first sights race on writing them. It is not a fully
  cold process: the in-memory cookie/crumb of the already-running session survives (cold
  requests were 1-2 each, like warm), so a brand-new process hitting 4 workers at once on its
  very first request is not covered.
- **Health check**: AAPL 5-day history; a 404, empty answer or exception prints
  `yahoo unhealthy: ...` and exits 2 (not exercised live; Yahoo was healthy).
