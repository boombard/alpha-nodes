---
id: TASK-5
title: M1.5 Run API and toy end-to-end scenarios
status: In Progress
assignee: []
created_date: '2026-11-23T08:02:42Z'
updated_date: '2026-11-23T09:01:30Z'
labels:
  - core
milestone: m-0
dependencies:
  - TASK-2
  - TASK-3
  - TASK-4
references:
  - documentation/design/core.md
  - documentation/design/lessons.md
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Integration task closing M1. It reproduces the engine-comparison spike's scenarios on the toy domain. Spec: `documentation/design/core.md` (Memoization escape hatches, Run configuration), `documentation/design/lessons.md` (Engine-comparison spike).

## Files
- Create: `packages/lensgraph/src/lensgraph/run.py`
- Modify: `packages/lensgraph/src/lensgraph/__init__.py` (public exports: `Node`, `FetchNode`, `TransformNode`, `CalcNode`, `NodeRegistry`, `build_plan`, `RunSpec`, `run`, `arun`, `CandidateRef`, `Absent`, `GlobalFailure`); `packages/lensgraph/tests/conftest.py` (move the `toy_registry` fixture here from task-2's tests)
- Test: `packages/lensgraph/tests/test_e2e_toy.py`

## Interfaces
Consumes:
- `build_plan`, `NodeRegistry` (task-2)
- `AsyncioExecutor`, `ResourceLimit` (task-3)
- `FileBlobStore`, `DuckDBRunIndex` (task-4)
- `RunAborted`, `RunResult` (task-1)

Produces:
```python
class RunSpec(BaseModel):                 # extra="forbid"
    targets: list[str]; candidates: list[CandidateRef]
    nodes: dict[str, dict[str, Any]] = {}            # per-node params
    limits: dict[str, ResourceLimit] = {}
    invalidate: list[str] = []; no_cache: bool = False
async def arun(spec: RunSpec, registry: NodeRegistry, *, store_root: Path,
               services: Mapping[str, Any] | None = None, executor: Executor | None = None,
               run_id: str | None = None) -> RunResult
def run(spec: RunSpec, registry: NodeRegistry, **kwargs: Any) -> RunResult   # asyncio.run(arun(...))
```
Semantics:
- **Stores:** `store_root/blobs` holds the `FileBlobStore`; `store_root/index.duckdb` holds the `DuckDBRunIndex`.
- **Memo bypass:** `bypass_memo` is `plan.descendants(set(spec.invalidate))`, or every key when `no_cache` is set.
- **Run records:** call `index.start_run(run_id, spec.model_dump(mode="json"))` before executing. After a normal completion, call `finish_run(run_id, "ok")`.
- **Abort:** `RunAborted` propagates to the caller.

## Steps
- [ ] Write the failing tests in `test_e2e_toy.py`, using `tmp_path` as the store root:
  - `test_fresh_run_outputs`: S1/S2 `growth_rate` are floats; S3 `growth_rate` is skipped with `failure.origin == "assay_clean"`; `result.status == "ok"`.
  - `test_identical_rerun_all_memoizable_cached`: on the second run, every ok node with `memoize=True` has `cache_hit=True`.
  - `test_param_change_reruns_only_descendants`: with `nodes={"growth_rate": {"window": 3}}`, `growth_rate` has `cache_hit=False` and `assay_clean` has `cache_hit=True`.
  - `test_invalidate_reruns_node_and_descendants`: `invalidate=["assay_clean"]`.
  - `test_no_cache_reruns_everything`
  - `test_abort_then_resume_from_cache`: the first run has `toy_source.fail_for={"S2"}` and raises `RunAborted`. The second run, with `fail_for` cleared, has `cache_hit=True` for every memoizable node that finished in the first run.
  - `test_results_persisted_in_index`: `DuckDBRunIndex(store_root/"index.duckdb").node_results(run_id)` has `len(plan.nodes)` rows.
  - `test_public_api_imports`: `from lensgraph import run, RunSpec, Node, NodeRegistry`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_e2e_toy.py -q`. Expected: FAIL.
- [ ] Implement `run.py` and the exports.
- [ ] Run `uv run pytest -q` (whole suite), then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): run API and toy end-to-end scenarios`.

**M1 demo gate (for the human):** paste the output of `uv run pytest -q` and `to_mermaid` for the toy graph into the task's final summary.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 run(RunSpec) executes on disk-backed stores and records the run in the index
- [ ] #2 Identical rerun is all cache hits for memoizable nodes; param change reruns only descendants
- [ ] #3 invalidate and no_cache escape hatches work
- [ ] #4 An aborted run resumes from cache on the next run
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
Worker: dispatch ctx_7de4e08bf563, worktree task-5
<!-- SECTION:NOTES:END -->
