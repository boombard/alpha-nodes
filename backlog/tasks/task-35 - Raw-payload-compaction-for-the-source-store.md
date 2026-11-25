---
id: TASK-35
title: Raw payload compaction for the source store
status: To Do
assignee: []
created_date: '2026-11-25T02:49:33Z'
labels:
  - core
  - sketch
dependencies:
  - TASK-30
references:
  - documentation/design/core.md
type: feature
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch, not planned in detail. Each raw provider response is one blob file. Daily top-ups across a ~2,000-ticker universe write ~2,000 small files a day (~700k a year), and renormalise re-reads every one. Pack raw payloads into one Parquet file per (dataset, provider, month), keeping every RawResponse.payload_hash resolvable (an index from hash to file and row), and make renormalise read packed files sequentially. Not needed at M4 demo scale; plan it when the universe grows (M7) or renormalise becomes slow.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Raw payloads can be compacted into per-(dataset, provider, month) Parquet files without changing any stored payload_hash or fact
- [ ] #2 renormalise over compacted raw gives the same facts as over uncompacted raw
- [ ] #3 Compaction is idempotent and safe to interrupt
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
