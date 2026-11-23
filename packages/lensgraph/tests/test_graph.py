"""Tests for plan building: resolution, validation, expansion, ordering and rendering."""

from typing import Any, ClassVar

import pytest
from lensgraph.graph import (
    GRAPH_RULES,
    CycleError,
    DuplicateCandidateError,
    GraphError,
    ParamsError,
    ScopeError,
    UnknownNodeError,
    build_plan,
    resolve_classes,
    to_mermaid,
)
from lensgraph.node import CalcNode, FetchNode, Node
from lensgraph.registry import NodeRegistry
from lensgraph.types import CandidateRef
from toy.nodes import AssayClean, AssayRaw, GrowthRate, ReferencePanel, ToxNotes


@pytest.fixture
def toy_registry() -> NodeRegistry:
    registry = NodeRegistry()
    for cls in (ReferencePanel, AssayRaw, AssayClean, GrowthRate, ToxNotes):
        registry.register(cls)
    return registry


def _node(
    name: str,
    inputs: dict[str, str] | None = None,
    optional: dict[str, str] | None = None,
    scope: str = "candidate",
) -> type[Node]:
    """Make a throwaway calc node class for graph-shape tests."""
    return type(
        name,
        (CalcNode,),
        {
            "__annotations__": {"name": ClassVar[str]},
            "name": name,
            "inputs": inputs or {},
            "optional_inputs": optional or {},
            "scope": scope,
        },
    )


def _registry_of(*classes: type[Node]) -> NodeRegistry:
    registry = NodeRegistry()
    for cls in classes:
        registry.register(cls)
    return registry


def test_resolves_transitive_deps_only_for_targets(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    plan = build_plan(["growth_rate"], toy_registry, toy_candidates)
    assert len(plan.nodes) == 10
    assert not any(k.name == "tox_notes" for k in plan.nodes)
    assert sum(1 for k in plan.nodes if k.name == "reference_panel") == 1


def test_shared_node_single_instance_and_deps_point_to_it(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    plan = build_plan(["growth_rate"], toy_registry, toy_candidates)
    shared = [k for k in plan.nodes if k.name == "reference_panel"]
    assert shared[0].candidate is None
    for key, planned in plan.nodes.items():
        if key.name == "growth_rate":
            assert planned.deps["reference"] == shared[0]
            assert planned.deps["assay"].candidate == key.candidate
    instances = {id(p.node) for k, p in plan.nodes.items() if k.name == "growth_rate"}
    assert len(instances) == 1


def test_topological_order(toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]) -> None:
    plan = build_plan(["growth_rate", "tox_notes"], toy_registry, toy_candidates)
    seen = set()
    for key, planned in plan.nodes.items():
        assert all(dep in seen for dep in planned.deps.values())
        seen.add(key)


def test_order_is_deterministic(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    first = list(build_plan(["growth_rate", "tox_notes"], toy_registry, toy_candidates).nodes)
    second = list(build_plan(["tox_notes", "growth_rate"], toy_registry, toy_candidates).nodes)
    assert first == second


def test_cycle_detected_with_path() -> None:
    registry = _registry_of(_node("a", {"x": "b"}), _node("b", {"x": "a"}))
    with pytest.raises(CycleError, match="a -> b -> a"):
        build_plan(["a"], registry, [CandidateRef(id="c1")])


def test_shared_depends_on_candidate_raises() -> None:
    registry = _registry_of(
        _node("per", scope="candidate"), _node("glob", {"x": "per"}, scope="shared")
    )
    with pytest.raises(ScopeError, match="glob"):
        build_plan(["glob"], registry, [CandidateRef(id="c1")])


def test_unknown_input_raises() -> None:
    registry = _registry_of(_node("a", {"x": "ghost"}))
    with pytest.raises(UnknownNodeError, match=r"unknown node 'ghost' \(input 'x' of 'a'\)"):
        build_plan(["a"], registry, [CandidateRef(id="c1")])


def test_unknown_target_raises(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    with pytest.raises(UnknownNodeError):
        build_plan(["ghost"], toy_registry, toy_candidates)


def test_params_applied_and_typo_rejected(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    plan = build_plan(
        ["growth_rate"], toy_registry, toy_candidates, node_params={"growth_rate": {"window": 3}}
    )
    node: Any = next(p.node for k, p in plan.nodes.items() if k.name == "growth_rate")
    assert node.window == 3
    with pytest.raises(ParamsError, match="growth_rate"):
        build_plan(
            ["growth_rate"], toy_registry, toy_candidates, node_params={"growth_rate": {"windw": 3}}
        )


def test_params_for_unresolved_node_rejected(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    with pytest.raises(ParamsError, match="tox_notes"):
        build_plan(["growth_rate"], toy_registry, toy_candidates, node_params={"tox_notes": {}})


def test_replacement_swaps_implementation(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    class OtherRaw(FetchNode):
        name: ClassVar[str] = "assay_raw"

    plan = build_plan(
        ["assay_clean"], toy_registry, toy_candidates, replacements={"assay_raw": OtherRaw}
    )
    node = next(p.node for k, p in plan.nodes.items() if k.name == "assay_raw")
    assert type(node) is OtherRaw


def test_replacement_name_mismatch_rejected(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    with pytest.raises(GraphError, match="assay_raw"):
        build_plan(
            ["assay_clean"], toy_registry, toy_candidates, replacements={"assay_raw": ToxNotes}
        )


def test_duplicate_candidate_ids_rejected(toy_registry: NodeRegistry) -> None:
    with pytest.raises(DuplicateCandidateError, match="S1"):
        build_plan(["growth_rate"], toy_registry, [CandidateRef(id="S1"), CandidateRef(id="S1")])


def test_optional_inputs_marked_optional() -> None:
    registry = _registry_of(_node("up"), _node("down", {"a": "up"}, {"b": "up"}))
    plan = build_plan(["down"], registry, [CandidateRef(id="c1")])
    planned = next(p for k, p in plan.nodes.items() if k.name == "down")
    assert planned.optional == frozenset({"b"})


def test_run_id_default_and_explicit(
    toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    assert build_plan(["tox_notes"], toy_registry, toy_candidates, run_id="r1").run_id == "r1"
    default = build_plan(["tox_notes"], toy_registry, toy_candidates).run_id
    stamp, suffix = default.split("-")
    assert len(stamp) == 15 and stamp[8] == "T"
    assert len(suffix) == 6


def test_descendants(toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]) -> None:
    plan = build_plan(["growth_rate"], toy_registry, toy_candidates)
    found = plan.descendants({"assay_clean"})
    assert {k.name for k in found} == {"assay_clean", "growth_rate"}
    assert len(found) == 6


def test_graph_rule_invoked(
    monkeypatch: pytest.MonkeyPatch, toy_registry: NodeRegistry, toy_candidates: list[CandidateRef]
) -> None:
    def forbid_all(classes: Any) -> None:
        raise GraphError(f"rule saw {sorted(classes)}")

    monkeypatch.setattr("lensgraph.graph.GRAPH_RULES", [*GRAPH_RULES, forbid_all])
    with pytest.raises(GraphError, match="rule saw"):
        build_plan(["tox_notes"], toy_registry, toy_candidates)


def test_resolve_classes_returns_closure(toy_registry: NodeRegistry) -> None:
    assert set(resolve_classes(["growth_rate"], toy_registry)) == {
        "growth_rate",
        "assay_clean",
        "assay_raw",
        "reference_panel",
    }


def test_to_mermaid_edges(toy_registry: NodeRegistry) -> None:
    classes = resolve_classes(["growth_rate"], toy_registry)
    text = to_mermaid(classes)
    assert text.startswith("flowchart LR")
    assert "assay_raw --> assay_clean" in text
    assert "reference_panel:::shared" in text
    optional = to_mermaid(
        resolve_classes(["down"], _registry_of(_node("up"), _node("down", {}, {"b": "up"})))
    )
    assert "up -.-> down" in optional
