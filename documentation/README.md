# alpha-nodes documentation

alpha-nodes is a rewrite of `alpha-capture` (itself a fork of `ai-hedge-fund`). It is a
**guard-railed "panel of lenses" framework**: a set of expert views (lenses, some
deterministic, some AI) assess each candidate and produce a structured, auditable
dossier. Finance (equity universe construction) is the first domain, built on top of a
domain-agnostic core.

## Design

Read in this order:

1. [design/overview.md](design/overview.md): intent, goals, non-goals, constraints,
   approaches considered, decision log, what's left to the builder.
2. [design/core.md](design/core.md): the generic library (`lensgraph`): nodes, graph,
   execution, failure semantics, memoization, verdicts and dossiers, AI guard rails,
   campaigns, artifact store, reporting.
3. [design/finance.md](design/finance.md): the finance package (`alpha_nodes`):
   datasets, providers, the point-in-time source store, the v1 lenses, the finance glossary
   ([entries](../packages/alpha_nodes/src/alpha_nodes/glossary/)), universe campaigns.
4. [design/lessons.md](design/lessons.md): what we learned from alpha-capture and from
   the engine-comparison spike. It explains *why* several decisions were made.

## Reference

- [reference/ta-lib/README.md](reference/ta-lib/README.md): verbatim snapshot of TA-Lib's
  per-function docs (formulas, inputs, params, defaults) with an index. Read it when choosing
  or specifying technical indicators.

## Workflow and plan

- [workflow.md](workflow.md): coordinator/worker loop, task rules, backlog usage.
- `backlog/`: Backlog.md tasks and milestones. The plan overview is `backlog/docs/doc-1 - Implementation-plan.md`.

## Status

- 2026-11-23: design written; M1–M2 planned in detail, M3–M8 sketched. Nothing implemented yet.
