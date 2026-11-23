---
id: m-3
title: "M4 Source store and yfinance prices"
---

## Description

Sketch. Generic point-in-time source store in lensgraph (raw layer, canonical facts with known_at, interval coverage, fetch-attempt log, TTL, as-of query, renormalise, repairs/checks); alpha_nodes package; canonical prices/profile/fx datasets; YFinanceProvider (pinned yfinance, repair=True, GBp handling); DatasetFetch node; canary script.

**Demo gate:** fetching 10 UK/AU/US tickers twice makes network calls only the first time; GBp tickers normalised; suspect rows visible.
