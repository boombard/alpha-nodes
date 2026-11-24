---
id: TASK-23
title: 'Live run view: observer hook, event log, d3 graph page'
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
Sketch only (noted 2026-11-24): a live screen while a run or campaign is going. Detail it when planning the milestone it lands in; long campaigns (M7) are what make it worth having.

## Scope sketch
- **Executor observer hook:** an `ExecutionObserver` protocol (`on_node_start`, `on_node_finish`, `on_run_finish`, plus waiting-on-resource if cheap) passed to `execute`. The default is a no-op.
- **Event sink behind an interface:** an `EventSink` protocol. The first implementation appends JSON lines to `<store>/runs/<run_id>/events.jsonl`, readable from any process while the run writes. DuckDB allows one writer process, so a viewer can't read the index mid-run. The log also survives crashes.
- **Live page:** `lensgraph run --live` serves a single page (FastAPI with server-sent events, or polling the event file). It draws the stored plan graph (`RunIndex.plan_graph`, TASK-19) with d3 (dagre or force layout), colours nodes by status as events arrive, and shows counters: done, failed, cache hits, LLM tokens and cost.
- **Campaigns:** per-stratum progress against quotas.

## Brokers (Redis, RabbitMQ), decided not now
Only worth it once execution is distributed across processes or machines. If that happens, prefer the planned Postgres index first (`SKIP LOCKED` work queues plus `LISTEN/NOTIFY` for live events, so no second piece of infrastructure). Use Redis if a shared cross-process rate limiter or fast pub/sub is needed (Streams for a durable event log). RabbitMQ is unlikely to be needed. Keeping `EventSink`, `Executor` and the resource limiter behind interfaces is what keeps that door open.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
