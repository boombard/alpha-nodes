"""In-process asyncio executor; see documentation/design/core.md, Execution, Failure
semantics and Memoization.
"""

import asyncio
import inspect
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from typing import Any

from ..hashing import content_hash, memo_key
from ..node import NodeContext
from ..plan import ExecutionPlan, NodeKey, NodeResult, NodeStatus, PlannedNode, RunResult
from ..store.base import BlobStore, RunIndex
from ..types import Absent, Failed, GlobalFailure, UpstreamFailed
from .base import RunAborted
from .limits import ResourceLimit, ResourceLimiter


class _RunState:
    """Mutable bookkeeping shared by the node tasks of one `execute` call."""

    def __init__(
        self,
        plan: ExecutionPlan,
        blobs: BlobStore,
        index: RunIndex,
        services: Mapping[str, Any],
        bypass_memo: AbstractSet[NodeKey],
        limiter: ResourceLimiter,
        max_concurrency: int,
    ) -> None:
        self.plan = plan
        self.blobs = blobs
        self.index = index
        self.services = dict(services)
        self.bypass_memo = bypass_memo
        self.limiter = limiter
        self.sem = asyncio.Semaphore(max_concurrency)
        self.done = {key: asyncio.Event() for key in plan.nodes}
        self.results: dict[NodeKey, NodeResult] = {}
        self.values: dict[NodeKey, Any] = {}
        self.hashes: dict[NodeKey, str] = {}  # output hashes of ok/recovered nodes

    def run_result(self, status: str) -> RunResult:
        """Snapshot of what has finished so far, in plan order."""
        ordered = {key: self.results[key] for key in self.plan.nodes if key in self.results}
        return RunResult(
            run_id=self.plan.run_id,
            status="aborted" if status == "aborted" else "ok",
            results=ordered,
            values=dict(self.values),
        )


class AsyncioExecutor:
    """Runs an ExecutionPlan with one asyncio task per node instance.

    Implements the `Executor` protocol. Each task awaits its dependencies, assembles inputs
    (applying failure propagation), consults the memo cache, runs the node under its resource
    limits (sync bodies in threads) and records the outcome. A `GlobalFailure` aborts the run.

    Args:
        limits: per-resource concurrency/rate limits, by `Node.resource` name.
        max_concurrency: cap on node bodies executing at once, across all resources.
    """

    def __init__(
        self, limits: Mapping[str, ResourceLimit] | None = None, max_concurrency: int = 32
    ) -> None:
        self._limits = dict(limits or {})
        self._max_concurrency = max_concurrency

    async def execute(
        self,
        plan: ExecutionPlan,
        blobs: BlobStore,
        index: RunIndex,
        *,
        services: Mapping[str, Any] | None = None,
        bypass_memo: AbstractSet[NodeKey] = frozenset(),
    ) -> RunResult:
        """Execute `plan`; the caller owns `index.start_run` and the final `finish_run`.

        Raises `RunAborted` (after `finish_run(..., "aborted")`) if any node raises
        `GlobalFailure`; the exception carries the results of nodes that finished.
        """
        state = _RunState(
            plan,
            blobs,
            index,
            services or {},
            bypass_memo,
            ResourceLimiter(self._limits),  # per execute: asyncio primitives are loop-bound
            self._max_concurrency,
        )
        tasks = [asyncio.create_task(self._node_task(state, p)) for p in plan.nodes.values()]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        except asyncio.CancelledError:
            await _cancel(tasks)
            raise
        errors = [exc for t in done if (exc := t.exception()) is not None]  # retrieves all
        error = next((e for e in errors if isinstance(e, GlobalFailure)), None) or next(
            iter(errors), None
        )
        if error is None:
            return state.run_result("ok")
        await _cancel(list(pending))
        if isinstance(error, GlobalFailure):
            index.finish_run(plan.run_id, "aborted")
            raise RunAborted(state.run_result("aborted"), error) from error
        raise error

    async def _node_task(self, state: _RunState, planned: PlannedNode) -> None:
        """Wait for dependencies, process the node and publish its completion.

        The done event is set only once the result is recorded; if `_process` raises, it stays
        unset so dependents remain blocked until the run cancels them.
        """
        for dep in set(planned.deps.values()):
            await state.done[dep].wait()
        await self._process(state, planned)
        state.done[planned.key].set()

    async def _process(self, state: _RunState, planned: PlannedNode) -> None:
        """Run one node instance through the assemble / check / memo / run / record pipeline."""
        node, key = planned.node, planned.key
        loop = asyncio.get_running_loop()
        started = loop.time()
        inputs: dict[str, Any] = {}
        input_hashes: dict[str, str] = {}
        upstream_failure: Failed | None = None  # first failed required dependency
        for kwarg, dep in planned.deps.items():
            dep_result = state.results[dep]
            if dep_result.status in ("ok", "recovered"):
                inputs[kwarg] = state.values[dep]
                input_hashes[kwarg] = state.hashes[dep]
                continue
            failure = dep_result.failure
            assert failure is not None
            if kwarg in planned.optional:
                inputs[kwarg] = Absent(reason=f"upstream '{failure.origin}' failed: {failure.error}")
                input_hashes[kwarg] = content_hash(inputs[kwarg])
            elif upstream_failure is None:
                upstream_failure = failure
        candidate = next((c for c in state.plan.candidates if c.id == key.candidate), None)
        ctx = NodeContext(
            run_id=state.plan.run_id,
            candidate=candidate,
            services=state.services,
            input_hashes=input_hashes,
        )

        status: NodeStatus = "ok"
        value: Any = None
        out_hash: str | None = None
        mkey: str | None = None
        cache_hit = False
        failure_out: Failed | None = None
        error: str | None = None
        try:
            if upstream_failure is not None:
                try:
                    value = node.validate_output(node.on_upstream_failure(ctx, upstream_failure))
                    status = "recovered"
                    out_hash = state.blobs.put(value)
                except UpstreamFailed as exc:
                    status, failure_out = "skipped", exc.failure
                    error = f"upstream '{exc.failure.origin}' failed: {exc.failure.error}"
            else:
                node.check_inputs(**inputs)
                if node.memoize:
                    mkey = memo_key(node, input_hashes, key.candidate, node.memo_salt(state.services))
                    cached = None if key in state.bypass_memo else state.index.lookup_memo(mkey)
                    if cached is not None and state.blobs.has(cached):
                        value, out_hash, cache_hit = state.blobs.get(cached), cached, True
                if not cache_hit:
                    value = node.validate_output(await self._invoke(state, planned, ctx, inputs))
                    out_hash = state.blobs.put(value)
                    if mkey is not None:
                        state.index.save_memo(mkey, out_hash)
        except GlobalFailure:
            raise
        except Exception as exc:  # noqa: BLE001  # node failure is data; see Failure semantics
            status, value, out_hash, mkey, cache_hit = "failed", None, None, None, False
            error = f"{type(exc).__name__}: {exc}"
            failure_out = Failed(origin=node.name, candidate=key.candidate, error=error)

        result = NodeResult(
            key=key,
            status=status,
            output_hash=out_hash,
            memo_key=mkey,
            cache_hit=cache_hit,
            error=error,
            failure=failure_out,
            duration_s=loop.time() - started,
        )
        if out_hash is not None:
            state.values[key], state.hashes[key] = value, out_hash
        state.results[key] = result
        state.index.record_node(state.plan.run_id, result)

    async def _invoke(
        self, state: _RunState, planned: PlannedNode, ctx: NodeContext, inputs: dict[str, Any]
    ) -> Any:
        """Call `node.run` under its resource slot and the global cap; sync bodies use threads."""
        node = planned.node
        async with state.limiter.slot(node.resource), state.sem:
            if inspect.iscoroutinefunction(node.run):
                return await node.run(ctx, **inputs)
            return await asyncio.to_thread(node.run, ctx, **inputs)


async def _cancel(tasks: list["asyncio.Task[None]"]) -> None:
    """Cancel `tasks` and wait for them to unwind."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
