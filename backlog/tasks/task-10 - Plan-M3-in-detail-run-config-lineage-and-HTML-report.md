---
id: TASK-10
title: 'Plan M3 in detail: run config, lineage and HTML report'
status: To Do
assignee: []
created_date: '2026-11-23T08:03:31Z'
labels:
  - plan
  - sketch
milestone: m-2
dependencies:
  - TASK-9
references:
  - documentation/design/core.md
type: task
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketched tasks (expected parallelism in brackets):
- M3.1 contracts: `RunConfig` YAML model (extends `RunSpec`: panel, profiles, limits, providers placeholder, report options), `Settings` (pydantic-settings: store root, `LENSGRAPH_*` env), CLI skeleton (`lensgraph run <yaml>`, `--invalidate`, `--no-cache`, `--profile`). [sequential]
- M3.2 lineage API: resolve a citable id `(run_id, candidate, node[, field|item])` to a stored output via `RunIndex` + `BlobStore`, plus a renderer registry (type -> HTML fragment: table, JSON, sparkline hook). [parallel with M3.3]
- M3.3 HTML report builder (Jinja2): run summary, per-candidate dossier pages, verdicts with claims whose citations link to rendered lineage views, flags and failures, Mermaid graph; static self-contained folder. [parallel with M3.2; renderer interface from M3.1]
- M3.4 toy report e2e and CLI wiring; snapshot-style assertions on the generated HTML structure (not pixels).

Design refs: core.md (Run configuration, Artifact store and run index, Reporting).

**Decided 2026-11-23:** `Dossier` has no `run_id` (node outputs must not carry run identity; see core.md, Verdicts and dossiers, Principles). Exports, reports and lineage views that hand a dossier out on its own wrap it at the edge in `DossierRecord(run_id, created_at, dossier)`, built outside the graph. Include that model in M3.1's contracts.

## How to do this task (coordinator/Opus, not a worker)
1. Re-read the milestone file, the design sections listed, and the code as it now stands.
2. Create this milestone's tasks with `backlog task create` in the format of task-1 to task-9:
   - Description sections: Files, Interfaces (Consumes/Produces with exact signatures), Steps (TDD, with test names and assertions), Out of scope.
   - Single-line ACs, `--dep` edges, the milestone, and labels.
   - The first task is a `contracts` task when the milestone introduces new shared interfaces.
   - Tasks that run concurrently touch disjoint files.
3. Re-point the next "Plan M…" task's dependency at this milestone's final task.
4. Get the human's approval of the new tasks before starting any of them.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
