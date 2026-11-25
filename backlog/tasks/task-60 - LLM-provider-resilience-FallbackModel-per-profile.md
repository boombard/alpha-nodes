---
id: TASK-60
title: 'LLM provider resilience: FallbackModel per profile'
status: To Do
assignee: []
created_date: '2026-11-25T08:18:24Z'
labels:
  - core
  - sketch
dependencies: []
references:
  - documentation/design/core.md
type: feature
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch, moved out of the M6 plan (TASK-13 note, 2026-11-24): real runs hit provider outages (repeated 529 Overloaded in M2). Consider pydantic-ai's `FallbackModel` per profile (e.g. Haiku via the Anthropic API, then via another provider). If adopted: provenance records the model that actually answered (not the first in the chain); the profile fingerprint covers the whole chain; a run can forbid fallback when comparability across candidates matters. Not needed for the M6 demo (15 candidates); revisit before M7 campaigns run hundreds of AI calls.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
