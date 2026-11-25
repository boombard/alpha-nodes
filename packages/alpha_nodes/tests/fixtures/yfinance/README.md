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
