"""Tests for AsyncioExecutor: ordering, failure semantics, memoization, limits, aborts."""

import asyncio
import time
from collections.abc import Mapping
from typing import Any, ClassVar

import pytest
from lensgraph.executor.asyncio_executor import AsyncioExecutor
from lensgraph.executor.base import RunAborted
from lensgraph.executor.limits import ResourceLimit
from lensgraph.node import CalcNode, FetchNode, Node, NodeContext
from lensgraph.plan import ExecutionPlan, NodeKey, PlannedNode, RunResult
from lensgraph.store.memory import InMemoryBlobStore, InMemoryRunIndex
from lensgraph.types import Absent, CandidateRef, Failed, GlobalFailure
from toy.nodes import AssayClean, AssayRaw, GrowthRate, ReferencePanel


def make_plan(
    node_instances: list[Node], candidates: list[CandidateRef], run_id: str = "r1"
) -> ExecutionPlan:
    """Hand-build a plan: `node_instances` must be in topological order."""
    nodes: dict[NodeKey, PlannedNode] = {}
    scope = {n.name: n.scope for n in node_instances}
    for node in node_instances:
        for cand in [None] if node.scope == "shared" else candidates:
            cid = cand.id if cand else None
            deps = {
                kwarg: NodeKey(name=up, candidate=None if scope[up] == "shared" else cid)
                for kwarg, up in node.all_inputs().items()
            }
            key = NodeKey(name=node.name, candidate=cid)
            nodes[key] = PlannedNode(
                key=key, node=node, deps=deps, optional=frozenset(node.optional_inputs)
            )
    return ExecutionPlan(run_id=run_id, candidates=candidates, nodes=nodes)


class SpyIndex(InMemoryRunIndex):
    """Run index that remembers which memo keys were saved."""

    def __init__(self) -> None:
        super().__init__()
        self.saved: list[str] = []

    def save_memo(self, memo_key: str, output_hash: str) -> None:
        self.saved.append(memo_key)
        super().save_memo(memo_key, output_hash)


class Env:
    """Executor plus shared stores, so one test can execute several plans against them."""

    def __init__(self, **executor_kwargs: Any) -> None:
        self.executor = AsyncioExecutor(**executor_kwargs)
        self.blobs = InMemoryBlobStore()
        self.index = SpyIndex()

    async def run(
        self,
        plan: ExecutionPlan,
        services: Mapping[str, Any] | None = None,
        bypass: frozenset[NodeKey] = frozenset(),
    ) -> RunResult:
        self.index.start_run(plan.run_id, {})
        return await self.executor.execute(
            plan, self.blobs, self.index, services=services, bypass_memo=bypass
        )


@pytest.fixture
def env() -> Env:
    return Env()


def k(name: str, cand: str | None = None) -> NodeKey:
    return NodeKey(name=name, candidate=cand)


# --- small purpose-built nodes ------------------------------------------------------------


class Boom(FetchNode):
    name: ClassVar[str] = "boom"
    output: ClassVar[Any] = int

    def run(self, ctx: NodeContext) -> int:
        raise ValueError("boom")


class Dependent(CalcNode):
    name: ClassVar[str] = "dependent"
    inputs: ClassVar[dict[str, str]] = {"x": "boom"}
    output: ClassVar[Any] = int

    def run(self, ctx: NodeContext, x: int) -> int:
        return x


class OptionalDependent(CalcNode):
    name: ClassVar[str] = "opt_dependent"
    optional_inputs: ClassVar[dict[str, str]] = {"x": "boom"}
    output: ClassVar[Any] = Absent

    def run(self, ctx: NodeContext, x: Any) -> Any:
        return x


class Recovering(Dependent):
    name: ClassVar[str] = "recovering"

    def on_upstream_failure(self, ctx: NodeContext, failure: Failed) -> int:
        return 7


class ReturnsNone(CalcNode):
    name: ClassVar[str] = "returns_none"
    output: ClassVar[Any] = float

    def run(self, ctx: NodeContext) -> Any:
        return None


class Logged(CalcNode):
    """Appends its own name to services['log'] and returns the sum of its inputs + 1."""

    name: ClassVar[str] = "logged"
    output: ClassVar[Any] = int

    def run(self, ctx: NodeContext, **inputs: int) -> int:
        ctx.services["log"].append(self.name)
        return sum(inputs.values()) + 1


class LogA(Logged):
    name: ClassVar[str] = "log_a"


class LogB(Logged):
    name: ClassVar[str] = "log_b"
    inputs: ClassVar[dict[str, str]] = {"a": "log_a"}


class LogC(Logged):
    name: ClassVar[str] = "log_c"
    inputs: ClassVar[dict[str, str]] = {"b": "log_b"}


class CutoffA(Logged):
    """Has a param `p` that does not affect its output (early-cutoff probe)."""

    name: ClassVar[str] = "cutoff_a"
    p: int = 1

    def run(self, ctx: NodeContext) -> int:
        ctx.services["log"].append(self.name)
        return 1


class CutoffB(Logged):
    name: ClassVar[str] = "cutoff_b"
    inputs: ClassVar[dict[str, str]] = {"a": "cutoff_a"}


class Flaky(CalcNode):
    name: ClassVar[str] = "flaky"
    output: ClassVar[Any] = int

    def run(self, ctx: NodeContext) -> int:
        if ctx.services["fail"]:
            raise RuntimeError("flaky")
        return 1


class SleepA(CalcNode):
    name: ClassVar[str] = "sleep_a"
    scope: ClassVar = "shared"
    output: ClassVar[Any] = int

    def run(self, ctx: NodeContext) -> int:
        time.sleep(0.2)
        return 1


class SleepB(SleepA):
    name: ClassVar[str] = "sleep_b"


class Limited(CalcNode):
    name: ClassVar[str] = "limited_1"
    scope: ClassVar = "shared"
    resource: ClassVar = "r"
    output: ClassVar[Any] = int

    async def run(self, ctx: NodeContext) -> int:
        state = ctx.services["state"]
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return 1


class Limited2(Limited):
    name: ClassVar[str] = "limited_2"


class Limited3(Limited):
    name: ClassVar[str] = "limited_3"


class Quick(CalcNode):
    name: ClassVar[str] = "quick"
    scope: ClassVar = "shared"
    output: ClassVar[Any] = int

    def run(self, ctx: NodeContext) -> int:
        return 1


class Outage(CalcNode):
    name: ClassVar[str] = "outage"
    scope: ClassVar = "shared"
    output: ClassVar[Any] = int

    async def run(self, ctx: NodeContext) -> int:
        await asyncio.sleep(0.05)
        raise GlobalFailure("provider down")


class Slow(CalcNode):
    name: ClassVar[str] = "slow"
    scope: ClassVar = "shared"
    output: ClassVar[Any] = int

    async def run(self, ctx: NodeContext) -> int:
        await asyncio.sleep(5)
        return 1


class SpyClean(AssayClean):
    """AssayClean that logs when run() is entered."""

    def run(self, ctx: NodeContext, raw: Any) -> Any:
        ctx.services["log"].append("run")
        return super().run(ctx, raw)


S1 = CandidateRef(id="S1")
S3 = CandidateRef(id="S3")


# --- tests ----------------------------------------------------------------------------------


async def test_runs_in_dependency_order(env: Env):
    plan = make_plan([LogC(), LogB(), LogA()][::-1], [S1])
    services = {"log": []}
    result = await env.run(plan, services)
    assert services["log"] == ["log_a", "log_b", "log_c"]
    assert result.status == "ok"
    assert result.values[k("log_c", "S1")] == 3


async def test_failure_skips_dependents_and_preserves_origin(env: Env, toy_source, toy_services):
    nodes = [ReferencePanel(), AssayRaw(), AssayClean(), GrowthRate()]
    result = await env.run(make_plan(nodes, [S1, S3]), toy_services)
    assert result.results[k("assay_clean", "S3")].status == "failed"
    skipped = result.results[k("growth_rate", "S3")]
    assert skipped.status == "skipped"
    assert skipped.failure is not None
    assert skipped.failure.origin == "assay_clean"
    assert skipped.failure.candidate == "S3"
    assert result.results[k("growth_rate", "S1")].status == "ok"
    assert k("growth_rate", "S3") not in result.values
    assert result.status == "ok"


async def test_output_contract_violation_fails_node_not_run(env: Env):
    result = await env.run(make_plan([ReturnsNone()], [S1]))
    res = result.results[k("returns_none", "S1")]
    assert res.status == "failed"
    assert res.error is not None and "ContractViolation" in res.error
    assert result.status == "ok"
    assert res.output_hash is None


async def test_optional_failed_input_passed_as_absent(env: Env):
    result = await env.run(make_plan([Boom(), OptionalDependent()], [S1]))
    assert result.results[k("opt_dependent", "S1")].status == "ok"
    value = result.values[k("opt_dependent", "S1")]
    assert value == Absent(reason="upstream 'boom' failed: ValueError: boom")


async def test_check_inputs_violation_fails_node(env: Env, toy_services):
    toy_services["log"] = []
    nodes = [AssayRaw(), SpyClean()]
    result = await env.run(make_plan(nodes, [S3]), toy_services)
    res = result.results[k("assay_clean", "S3")]
    assert res.status == "failed"
    assert res.error is not None and "od600" in res.error
    assert toy_services["log"] == []


async def test_recovery_hook_value_used_status_recovered_not_memoized(env: Env):
    result = await env.run(make_plan([Boom(), Recovering()], [S1]))
    res = result.results[k("recovering", "S1")]
    assert res.status == "recovered"
    assert result.values[k("recovering", "S1")] == 7
    assert res.memo_key is None
    assert env.index.saved == []


async def test_memo_hit_on_second_execute(env: Env, toy_source, toy_services):
    nodes = [ReferencePanel(), AssayRaw(), AssayClean(), GrowthRate()]
    cands = [CandidateRef(id="S1"), CandidateRef(id="S2")]
    await env.run(make_plan(nodes, cands, "r1"), toy_services)
    calls_first = len(toy_source.calls)
    second = await env.run(make_plan(nodes, cands, "r2"), toy_services)
    assert len(toy_source.calls) == 2 * calls_first
    for cand in ("S1", "S2"):
        assert second.results[k("assay_clean", cand)].cache_hit
        assert second.results[k("growth_rate", cand)].cache_hit
        assert not second.results[k("assay_raw", cand)].cache_hit
    assert not second.results[k("reference_panel")].cache_hit
    assert second.values[k("growth_rate", "S1")] == pytest.approx(
        (await env.run(make_plan(nodes, cands, "r3"), toy_services)).values[k("growth_rate", "S1")]
    )


async def test_early_cutoff(env: Env):
    services = {"log": []}
    await env.run(make_plan([CutoffA(p=1), CutoffB()], [S1], "r1"), services)
    second = await env.run(make_plan([CutoffA(p=2), CutoffB()], [S1], "r2"), services)
    assert not second.results[k("cutoff_a", "S1")].cache_hit
    assert second.results[k("cutoff_b", "S1")].cache_hit
    assert services["log"] == ["cutoff_a", "cutoff_b", "cutoff_a"]


async def test_failures_not_memoized(env: Env):
    plan = make_plan([Flaky()], [S1], "r1")
    first = await env.run(plan, {"fail": True})
    assert first.results[k("flaky", "S1")].status == "failed"
    assert env.index.saved == []
    second = await env.run(make_plan([Flaky()], [S1], "r2"), {"fail": False})
    res = second.results[k("flaky", "S1")]
    assert res.status == "ok" and not res.cache_hit


async def test_bypass_memo_forces_rerun(env: Env):
    services = {"log": []}
    await env.run(make_plan([LogA()], [S1], "r1"), services)
    hit = await env.run(make_plan([LogA()], [S1], "r2"), services)
    assert hit.results[k("log_a", "S1")].cache_hit
    forced = await env.run(
        make_plan([LogA()], [S1], "r3"), services, bypass=frozenset([k("log_a", "S1")])
    )
    assert not forced.results[k("log_a", "S1")].cache_hit
    assert services["log"] == ["log_a", "log_a"]


async def test_sync_nodes_run_concurrently_in_threads(env: Env):
    start = time.monotonic()
    await env.run(make_plan([SleepA(), SleepB()], [S1]))
    assert time.monotonic() - start < 0.35


async def test_resource_limit_concurrency_one():
    env = Env(limits={"r": ResourceLimit(concurrency=1)})
    state = {"active": 0, "peak": 0}
    result = await env.run(make_plan([Limited(), Limited2(), Limited3()], [S1]), {"state": state})
    assert state["peak"] == 1
    assert all(r.status == "ok" for r in result.results.values())


async def test_global_failure_aborts_and_records_completed(env: Env):
    plan = make_plan([Quick(), Outage(), Slow()], [S1])
    with pytest.raises(RunAborted) as excinfo:
        await env.run(plan)
    aborted = excinfo.value
    assert isinstance(aborted.cause, GlobalFailure)
    assert aborted.result.status == "aborted"
    assert aborted.result.results[k("quick")].status == "ok"
    assert k("slow") not in aborted.result.results
    assert env.index.runs["r1"]["status"] == "aborted"
    assert [r.status for r in env.index.node_results("r1")] == ["ok"]


class OutageFetch(FetchNode):
    name: ClassVar[str] = "outage_fetch"
    output: ClassVar[Any] = int

    async def run(self, ctx: NodeContext) -> int:
        raise GlobalFailure("provider down")


class AfterOutage(CalcNode):
    name: ClassVar[str] = "after_outage"
    inputs: ClassVar[dict[str, str]] = {"x": "outage_fetch"}
    output: ClassVar[Any] = int

    def run(self, ctx: NodeContext, x: int) -> int:
        return x


async def test_global_failure_with_dependents_always_raises_run_aborted():
    """Dependents of a GlobalFailure node must never surface a KeyError (a wake-up race)."""
    cands = [CandidateRef(id=f"S{i}") for i in range(4)]
    for _ in range(100):
        env = Env()
        plan = make_plan([OutageFetch(), AfterOutage()], cands)
        with pytest.raises(RunAborted):
            await env.run(plan)
