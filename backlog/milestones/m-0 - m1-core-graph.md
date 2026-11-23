---
id: m-0
title: "M1 Core graph"
---

## Description

Workspace, node contracts, graph build/validation, asyncio executor with failure semantics, memoization with persistent blob store + DuckDB run index, toy non-finance domain.

**Demo gate:** toy e2e test suite green; rerun of an unchanged toy run is all cache hits for memoizable nodes; `to_mermaid` output reviewed.
