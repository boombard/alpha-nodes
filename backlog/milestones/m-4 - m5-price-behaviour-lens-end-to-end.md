---
id: m-4
title: "M5 Price-behaviour lens end-to-end"
---

## Description

Detailed 2026-11-25 (TASK-12). Calculation layers per finance.md: numpy kernels -> frame adapters -> calc nodes.

TASK-43 M5.1 contracts -> {TASK-45 M5.3 adapters + calc nodes (also after TASK-44 M5.2 kernels), TASK-46 M5.4 price_behaviour lens, TASK-47 M5.5 run-view charts} -> TASK-48 M5.6 registry, 50-ticker run, e2e. TASK-44 has no dependencies and runs alongside TASK-43.

**Demo gate:** a live 50-ticker run gives an HTML report with a dossier per candidate, where claims drill down to the metrics and the price chart. Rerunning after a threshold change recomputes only the lens and the aggregator.
