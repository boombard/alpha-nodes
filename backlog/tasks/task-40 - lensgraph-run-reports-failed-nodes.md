---
id: TASK-40
title: lensgraph run reports failed nodes
status: In Progress
assignee: []
created_date: '2026-11-25T05:31:05Z'
updated_date: '2026-11-25T05:40:36Z'
labels:
  - lensgraph
dependencies: []
references:
  - documentation/design/core.md
type: feature
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`lensgraph run` prints only `run id`, `store` and `report`, so a run with failed nodes looks the same as a clean one. Found in the M4 demo (TASK-34): prices for SAP.DE and MC.PA failed in every run while the CLI printed nothing about it and exited 0. Exit 0 stays (core.md, CLI: "failed nodes are data"); this task only makes failures visible. Spec: `documentation/design/core.md` (CLI, Failure semantics).

## Files
- Modify: `packages/lensgraph/src/lensgraph/cli.py` (`run_command`), `documentation/design/core.md` (CLI section)
- Test: `packages/lensgraph/tests/test_cli.py`

## Behaviour
- After `run id:` / `store:`, print a `nodes:` line with counts by status, e.g. `nodes: 21 ok, 2 failed, 3 skipped` (omit zero counts).
- Then one line per failed node: `failed: <node> [<candidate>]: <first line of the error>`, capped at 20 lines with `… and N more`. Skipped nodes are counted, not listed.
- Same output for an aborted run (from `RunAborted.result`), before the stderr error line's exit.
- Exit codes unchanged.
- Uses the toy domain in tests; no finance concepts in lensgraph.

## Steps
- [ ] Failing tests in `test_cli.py` with a toy config that has a failing node: the `nodes:` counts line, the `failed:` line (node, candidate, error), the cap, and exit 0 still.
- [ ] Implement in `run_command` (a small helper that formats the result's node statuses; reuse the run result's existing status fields).
- [ ] Update core.md CLI section.
- [ ] `uv run pytest -q`, ruff, pyright.
- [ ] Commit: `feat(lensgraph): run CLI reports node status counts and failed nodes`.

Out of scope: changing exit codes, `sources status` output.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 lensgraph run prints node counts by status and one line per failed node (capped), for completed and aborted runs
- [ ] #2 Exit codes unchanged; core.md CLI section documents the output
- [ ] #3 Tested with a toy failing node in test_cli.py
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_ff0a1c773ece, worktree task-40
<!-- SECTION:NOTES:END -->
