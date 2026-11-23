---
id: m-0
title: "M1 Core graph"
---

## Description

Workspace, node contracts, graph build/validation, asyncio executor with failure semantics, memoization with persistent blob store + DuckDB run index, toy non-finance domain.

**Demo gate:** toy e2e test suite green; rerun of an unchanged toy run is all cache hits for memoizable nodes; `to_mermaid` output reviewed.

**Signed off 2026-11-23** by the human: 121 tests passing on main at c81a07b; rerun all cache hits (test_identical_rerun_all_memoizable_cached); to_mermaid output reviewed (see TASK-5 final summary).
