---
id: TASK-23
title: 'Live run view: events, API and live DataSource for the run view app'
status: To Do
assignee: []
created_date: '2026-11-24T01:16:19Z'
labels:
  - core
  - sketch
milestone: m-6
dependencies:
  - TASK-22
references:
  - documentation/design/core.md
type: feature
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch only (noted 2026-11-24, restructured the same day): the live screen is **the same React app as the report** (TASK-24) with a live `DataSource`. Detail it when planning the milestone it lands in; long campaigns (M7) are what make it worth having.

## Scope sketch
- **Event model (Python, pydantic):** `RunEvent` (run_started with the PlanGraph, node_started, node_finished with its NodeResult, llm_call, dossier_ready, run_finished). Invariant: **folding all of a run's events over an empty `RunView` gives exactly `build_run_view(...)`**, tested in Python with a reducer mirrored in TS. Generate the TS event types from the models, as for `RunView`.
- **Executor observer hook:** an `ExecutionObserver` protocol (`on_node_start`, `on_node_finish`, `on_run_finish`) passed to `execute`; no-op by default. It emits `RunEvent`s.
- **Event sink behind an interface (`EventSink`):** the first implementation appends JSON lines to `<store>/runs/<run_id>/events.jsonl`, readable from any process while the run writes. DuckDB allows one writer process, so a viewer can't read the index mid-run. The log also survives crashes.
- **API:** `lensgraph run --live` (or `lensgraph serve`) runs a small FastAPI app: `GET /api/runs/{id}` returns the current `RunView`, and `GET /api/runs/{id}/events` streams server-sent events. It serves the same bundled `index.html`.
- **UI:** a `LiveSource` implementing `DataSource.subscribe`. The app's store applies events with the shared reducer: nodes change colour on the plan graph, candidates appear as dossiers land, and the counters (tokens, cost, cache hits) tick.
- **Campaigns:** per-stratum progress against quotas, as extra event types.

## Brokers (Redis, RabbitMQ), decided not now
Only worth it once execution is distributed across processes or machines. If that happens, prefer the planned Postgres index first (`SKIP LOCKED` work queues plus `LISTEN/NOTIFY` for live events, no second piece of infrastructure). Use Redis if a shared cross-process rate limiter or fast pub/sub is needed (Streams for a durable event log). RabbitMQ is unlikely to be needed. Keeping `EventSink`, `Executor`, the resource limiter and `DataSource` behind interfaces keeps that door open.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
