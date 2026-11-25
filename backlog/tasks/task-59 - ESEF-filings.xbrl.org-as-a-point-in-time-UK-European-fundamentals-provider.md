---
id: TASK-59
title: ESEF / filings.xbrl.org as a point-in-time UK/European fundamentals provider
status: To Do
assignee: []
created_date: '2026-11-25T08:18:24Z'
labels:
  - finance
  - sketch
  - research
dependencies: []
references:
  - documentation/design/finance.md
type: feature
ordinal: 59000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch from the M6 plan (TASK-13, 2026-11-25); finance.md Known data limitations names it as an *unverified* lead. Listed UK/EU companies file annual reports in ESEF (iXBRL, IFRS taxonomy); filings.xbrl.org may serve them with filing dates for free, which would give UK/European fundamentals `pit_reliable=true` and deeper history than yfinance's ~4 years. First step is research only: coverage for the canary set (BP.L, HSBA.L, VOD.L, ASML.AS, SAP.DE, NESN.SW, NOVO-B.CO, BOOT.L), API terms and rate limits, filing-date availability, and how the `ifrs-full` tags map onto the canonical line items. Output: a findings note in finance.md and, if viable, a provider task that slots in as `fundamentals: [edgar, esef, yfinance]`.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
