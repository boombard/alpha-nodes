---
id: TASK-3
title: M1.3 Asyncio executor with failure semantics and memoization
status: In Review
assignee: []
created_date: '2026-11-23T08:02:42Z'
updated_date: '2026-11-23T08:42:33Z'
labels:
  - core
milestone: m-0
dependencies:
  - TASK-1
references:
  - documentation/design/core.md
type: feature
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec: `documentation/design/core.md`, sections Execution, Failure semantics and Memoization. Runs in parallel with task-2 and task-4.

## Files
- Create: `packages/lensgraph/src/lensgraph/executor/asyncio_executor.py`, `packages/lensgraph/src/lensgraph/executor/limits.py`
- Test: `packages/lensgraph/tests/test_executor.py`, `packages/lensgraph/tests/test_limits.py`. Build plans **by hand** with a local helper `make_plan(node_instances, candidates) -> ExecutionPlan` in `test_executor.py`, because `build_plan` (task-2) lands concurrently. Use `InMemoryBlobStore`/`InMemoryRunIndex` from task-1.

## Interfaces
Consumes (task-1): `Executor`, `RunAborted`, `ExecutionPlan`, `PlannedNode`, `NodeKey`, `NodeResult`, `RunResult`, `NodeContext`, `Node`, `Absent`, `Failed`, `UpstreamFailed`, `GlobalFailure`, `ContractViolation`, `content_hash`, `memo_key`, `BlobStore`, `RunIndex`.

Produces:
```python
class ResourceLimit(BaseModel): concurrency: int = 4; per_second: float | None = None
class ResourceLimiter:
    def __init__(self, limits: Mapping[str, ResourceLimit]) -> None
    def slot(self, resource: str | None) -> AbstractAsyncContextManager[None]   # None or unknown -> no limit
class AsyncioExecutor:   # implements Executor
    def __init__(self, limits: Mapping[str, ResourceLimit] | None = None, max_concurrency: int = 32) -> None
```
Semantics (per planned node, one asyncio task awaiting its deps' completion events):
1. **Assemble inputs.**
   - A required dep with status `ok` or `recovered` supplies its value.
   - A required dep with status `failed` or `skipped` triggers `node.on_upstream_failure(ctx, dep_failure)`:
     - If that raises `UpstreamFailed`, the node's status is `skipped`, `failure` is the dep's `Failed` (origin preserved), and it is not run.
     - If it returns a value, that value is validated and the status is `recovered`. It is not memoized.
   - An optional dep that failed or was skipped is passed as `Absent(reason=f"upstream '{origin}' failed: {error}")`.
2. **Memo lookup.**
   - `ctx.input_hashes` holds the hashes of the input values, with `Absent` hashed like any other value.
   - If `node.memoize` is true and the key is not in `bypass_memo`, compute `k = memo_key(node, ctx.input_hashes, cand, node.memo_salt(services))`. When `index.lookup_memo(k)` returns a hash whose blob exists, the status is `ok` with `cache_hit=True`.
3. **Check inputs.** Call `node.check_inputs(**inputs)` before the memo lookup's result is used and before running. A `ContractViolation` fails the node, as in step 4.
4. **Run** inside `limiter.slot(node.resource)`. A coroutine function is awaited; a sync function runs in `asyncio.to_thread`. The node's output then goes through `validate_output`.
5. **On exception:**
   - `GlobalFailure`: cancel all pending tasks, record the finished ones, `finish_run(..., "aborted")`, and raise `RunAborted(result, cause)`.
   - Any other exception, `ContractViolation` included: the status is `failed` with `Failed(origin=node.name, candidate=..., error=f"{type(e).__name__}: {e}")`. Failures are never memoized.
6. **On success:** `h = blobs.put(value)`. If memoizable, `save_memo(k, h)`. Then `record_node`.

`index.start_run`/`finish_run` are called by the caller (task-5), not by the executor, except `finish_run("aborted")` in step 4. `RunResult.values` holds every ok or recovered value.

## Steps
- [ ] Write the failing tests:
  - `test_runs_in_dependency_order`
  - `test_failure_skips_dependents_and_preserves_origin`: for S3, `assay_clean` fails and `growth_rate` is skipped with `failure.origin == "assay_clean"`; S1 is ok.
  - `test_output_contract_violation_fails_node_not_run`: a test node returning `None` for `output = float` ends `failed`, and the run completes.
  - `test_optional_failed_input_passed_as_absent`
  - `test_check_inputs_violation_fails_node`: S3 `assay_clean` fails at `check_inputs`, the error names `od600`, and `run` is never called.
  - `test_recovery_hook_value_used_status_recovered_not_memoized`
  - `test_memo_hit_on_second_execute`: on the second `execute` with the same stores, transform and calc nodes have `cache_hit=True`, and fetch nodes ran again (`toy_source.calls` doubled).
  - `test_early_cutoff`: test node A has a param `p` that doesn't change its output, and B depends on A. Changing `p` reruns A, and B is a cache hit.
  - `test_failures_not_memoized`: the node fails, then succeeds on the second run.
  - `test_bypass_memo_forces_rerun`
  - `test_sync_nodes_run_concurrently_in_threads`: two sync nodes each `time.sleep(0.2)` finish in under 0.35 s of wall time.
  - `test_resource_limit_concurrency_one`: the maximum simultaneous count observed for resource `"r"` is 1.
  - `test_global_failure_aborts_and_records_completed`: `RunAborted` is raised, `result.status == "aborted"`, and the nodes finished before the failure are recorded `ok`.
  - `test_limits.py::test_per_second_rate`: 5 acquisitions at `per_second=10` take at least 0.4 s.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_executor.py packages/lensgraph/tests/test_limits.py -q`. Expected: FAIL.
- [ ] Implement `limits.py` (semaphore plus a token bucket; `aiolimiter` is allowed) and `asyncio_executor.py`.
- [ ] Run the tests above, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): asyncio executor with failure propagation, memoization, resource limits`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Failed or contract-violating nodes are failed; dependents skipped with the original origin; optional inputs become Absent
- [ ] #2 on_upstream_failure recovery yields status recovered and is never memoized
- [ ] #3 Memo hits on rerun for memoizable nodes; fetch nodes always run; early cutoff works; failures never memoized
- [ ] #4 GlobalFailure aborts the run with RunAborted carrying completed results
- [ ] #5 Per-resource concurrency and rate limits enforced; sync nodes run in threads
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
Worker: dispatch ctx_2989043fe59e, worktree task-3
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_2989043fe59e, branch boom/task-3, 2 commits c4a32a4..8c7965b): AsyncioExecutor (one asyncio task per node instance; assemble, check, memo, run, record) plus ResourceLimit and ResourceLimiter. ACs 1-5 met (failure_skips_dependents, output_contract_violation, optional_failed_input, check_inputs, recovery_hook, memo_hit, early_cutoff, failures_not_memoized, bypass_memo, sync_nodes_concurrently, resource_limit_concurrency_one, global_failure_aborts, test_limits::test_per_second_rate). Coordinator re-ran checks: pytest 45 passed, ruff clean, pyright 0 errors.
Coordinator review: the pipeline order and failure semantics match the spec. A probe found a race: a GlobalFailure in a node with dependents raised KeyError instead of RunAborted in 12 of 200 runs. Fixed in one round: the done event is set only after the result is recorded, and GlobalFailure is preferred when choosing the error. A regression test runs the case 100 times, and the probe now gives 200 of 200 RunAborted. Reviewed by hand plus the probe; the code-review skill was not run.
Worker rulings: (1) the rate limit is even pacing (starts spaced 1/per_second apart), not a burst bucket; there is no aiolimiter dependency. (2) The limiter and semaphores are built per execute(), because asyncio primitives are loop-bound. (3) The resource slot is taken before the global max_concurrency semaphore, to avoid hold-and-wait. (4) check_inputs runs before the memo lookup; input hashes reuse the upstream output hashes. (5) Recovered values are blob-stored but never memoized. (6) Non-Global exceptions escaping a node task (executor bugs) are re-raised after cancelling the rest.
Open points: sync nodes in threads keep running after an abort (threads can't be cancelled). NodeContext.as_of is not set by the executor yet (no as_of in the plan until M8). If record_node or save_memo raises, the error escapes as an executor error, not a node failure.
<!-- SECTION:FINAL_SUMMARY:END -->
