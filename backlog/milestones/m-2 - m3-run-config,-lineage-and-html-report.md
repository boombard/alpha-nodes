---
id: m-2
title: "M3 Run config, lineage and HTML report"
---

## Description

Sketch. YAML RunConfig + pydantic-settings + CLI; lineage resolution (citable id -> stored output view); static HTML report with renderer registry and graph diagram; toy report e2e.

**Demo gate:** `uv run lensgraph run <toy.yaml>` writes a report you can open and drill from a claim to its cited data.

**Signed off 2026-11-24** by the human: 330 Python tests, 49 UI tests and the Playwright e2e passing on main at cd6d49d; `uv run lensgraph run packages/lensgraph/tests/toy/toy_run.yaml --path packages/lensgraph/tests` wrote .lensgraph/reports/20261124T081845-b84c34/index.html, reviewed with claim-to-cited-data drill-down. The report became the React run view (TASK-21/24) during the milestone.
