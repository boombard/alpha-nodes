"""The plan graph persisted at run start, readable from both run index implementations."""

from pathlib import Path

import pytest
from lensgraph.graph import build_plan
from lensgraph.plan import ExecutionPlan, NodeKey
from lensgraph.store.base import RunIndex
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.store.memory import InMemoryRunIndex
from toy.growth_lens import GrowthLens


@pytest.fixture(params=["memory", "duckdb"])
def index(request: pytest.FixtureRequest, tmp_path: Path) -> RunIndex:
    return InMemoryRunIndex() if request.param == "memory" else DuckDBRunIndex(tmp_path / "i.duckdb")


@pytest.fixture
def plan(ai_registry, toy_candidates) -> ExecutionPlan:
    ai_registry.register(GrowthLens)
    return build_plan(["safety_lens", "growth_lens"], ai_registry, toy_candidates, run_id="r1")


def test_plan_graph_roundtrip(index: RunIndex, plan: ExecutionPlan) -> None:
    index.start_run("r1", {})
    index.record_plan("r1", plan)
    graph = index.plan_graph("r1")
    assert [n.key for n in graph.nodes] == list(plan.nodes)
    assert len({str(n.key) for n in graph.nodes}) == len(graph.nodes)  # shared nodes once
    assert len(graph.edges) == sum(len(p.deps) for p in plan.nodes.values())
    kinds = {n.key.name: n.kind for n in graph.nodes}
    assert kinds["reference_panel"] == "fetch" and kinds["assay_clean"] == "transform"
    assert kinds["growth_rate"] == "calc" and kinds["safety_lens"] == "lens"
    assert next(n for n in graph.nodes if n.key.name == "reference_panel").scope == "shared"
    optional = {(e.source.name, e.target.name, e.kwarg) for e in graph.edges if e.optional}
    assert optional == {("tox_notes", "safety_lens", "tox_notes")}
    edge = next(e for e in graph.edges if e.kwarg == "reference")
    assert edge.source == NodeKey(name="reference_panel", candidate=None) and not edge.optional
