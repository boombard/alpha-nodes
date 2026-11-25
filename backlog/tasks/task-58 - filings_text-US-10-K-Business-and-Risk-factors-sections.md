---
id: TASK-58
title: 'filings_text: US 10-K Business and Risk factors sections'
status: To Do
assignee: []
created_date: '2026-11-25T08:18:23Z'
labels:
  - finance
  - sketch
dependencies: []
references:
  - documentation/design/finance.md
type: feature
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch, deferred from the M6 plan (TASK-13, 2026-11-25). A `filings_text` dataset (filing date axis or a snapshot keyed by accession) holding the 10-K Item 1 (Business) and Item 1A (Risk factors) sections for US names, from EDGAR filing documents, as an extra `quality_value` text input. Deferred because it is US-only while the market focus is UK/Europe, and section extraction from 10-K HTML is fragile (layouts vary; tables of contents repeat the headings). The profile business summary covers every region meanwhile. If built: an EDGAR adapter beside company facts, length-capped sections, known_at = filing date, and a quality check that the extracted section is non-trivial.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
