---
id: m-3
title: "M4 Source store and yfinance prices"
---

## Description

Sketch. Generic point-in-time source store in lensgraph (raw layer, canonical facts with known_at, interval coverage, fetch-attempt log, TTL, as-of query, renormalise, repairs/checks); alpha_nodes package; canonical prices/profile/fx datasets; YFinanceProvider (pinned yfinance, repair=True, GBp handling); DatasetFetch node; canary script.

**Demo gate:** fetching 10 UK/European tickers (plus one US) twice makes network calls only the first time; GBp tickers normalised; live bars never stored; suspect rows visible.

**Signed off 2026-11-25** by the human (landing TASK-34 via backlog-converge after reviewing the demo results): 626 Python tests passing on main at 91b920e. Demo run by a worker in the task-34 worktree with `runs/m4_prices.yaml` over 11 tickers: run 2 made no network calls; GBp tickers normalised (BP.L 5.44 GBP); no live bar stored (latest 2026-11-24); `sources status --suspect` listed 6 NOK fx_jump rows and 5 zero-volume holiday bars; the offline rerun had 23/23 nodes ok. The first demo run found a source-store bug (DuckDB list-type inference failed on SAP.DE/MC.PA 10y histories), fixed in the same task. Follow-up: TASK-40 (run CLI reports failed nodes).
