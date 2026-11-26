---
id: TASK-65
title: 'Glossary in the browser: standalone page and term links from run reports'
status: To Do
assignee: []
created_date: '2026-11-26T00:28:29Z'
labels:
  - core
  - sketch
dependencies:
  - TASK-63
  - TASK-64
references:
  - documentation/design/core.md
type: feature
ordinal: 65000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch, parked (user, 2026-11-26). Not planned in detail; do not dispatch until planned.

Bring the glossary (core.md "Glossary", TASK-63) into the browser:
- a standalone glossary page in the run view app (`packages/lensgraph-ui`): entries grouped by `category`, search over name, abbreviations and aliases, KaTeX-rendered math, relative `.md` links rewritten to the app's glossary route, a status badge (draft / verified);
- term links and `summary` tooltips on cited fields in a run report: `build_run_view` attaches the term id to each field cite (entries list `fields` as `ResultModel.field`, and the builder knows each cited output's model);
- `run.json` embeds the subset of entries the run cited, with the glossary `content_hash`, so an old report shows the definitions as they were when it ran;
- the contract is `Glossary.export()` (`GlossaryExport`), with TS types generated like RunView's.

Open questions for planning: embed the whole glossary or only cited entries in run.json; one app route or a separate static glossary site; whether the CLI writes `glossary.json` next to reports.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
