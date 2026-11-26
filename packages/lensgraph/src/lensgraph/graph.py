"""Plan building: resolve target nodes into a validated per-candidate ExecutionPlan.

See documentation/design/core.md, Graph. Validation rules live in `GRAPH_RULES` so later
milestones can append their own.
"""

import heapq
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .node import Node
from .plan import ExecutionPlan, NodeKey, PlannedNode
from .types import CandidateRef

if TYPE_CHECKING:
    from .registry import NodeRegistry


class GraphError(ValueError):
    """Base class of every plan-building failure."""


class UnknownNodeError(GraphError):
    """A target or input names a node that is not registered."""


class CycleError(GraphError):
    """The node dependency graph contains a cycle; the message shows the path."""


class ScopeError(GraphError):
    """A shared-scope node depends on a candidate-scope node."""


class DuplicateCandidateError(GraphError):
    """Two candidates share an id."""


class ParamsError(GraphError):
    """Node params are invalid or name a node that is not in the resolved graph."""


GraphRule = Callable[[Mapping[str, type[Node]]], None]
"""A validation rule over the resolved classes; raises GraphError on violation."""


def _check_scope(classes: Mapping[str, type[Node]]) -> None:
    """Rule: a shared node may not depend on a candidate-scope node."""
    for name, cls in classes.items():
        if cls.scope != "shared":
            continue
        for dep in cls.all_inputs().values():
            if classes[dep].scope == "candidate":
                raise ScopeError(f"shared node {name!r} depends on candidate node {dep!r}")


class LensDependencyError(GraphError):
    """A lens depends on another lens's verdict without being a `consumes_verdicts` node."""


def lens_dependency_rule(classes: Mapping[str, type[Node]]) -> None:
    """Rule: only `consumes_verdicts` nodes may take a LensNode as input (lenses never chain)."""
    from .lens import LensNode  # local import: keeps graph.py free of an import cycle

    for name, cls in classes.items():
        if cls.consumes_verdicts:
            continue
        for dep in cls.all_inputs().values():
            if issubclass(classes[dep], LensNode):
                raise LensDependencyError(
                    f"{name!r} depends on lens {dep!r} but does not consume verdicts"
                )


GRAPH_RULES: list[GraphRule] = [_check_scope, lens_dependency_rule]
"""Rules run by `build_plan` on the resolved classes; later milestones append to it."""


def resolve_classes(
    targets: Sequence[str],
    registry: "NodeRegistry",
    replacements: Mapping[str, type[Node]] | None = None,
) -> dict[str, type[Node]]:
    """Transitive closure of `targets` over `all_inputs()`, as name -> class.

    `replacements` override registry entries (their `.name` must match). Raises
    UnknownNodeError, CycleError or GraphError (replacement name mismatch).
    """
    replacements = replacements or {}
    for name, cls in replacements.items():
        if cls.name != name:
            raise GraphError(f"replacement for {name!r} is named {cls.name!r}")
    classes: dict[str, type[Node]] = {}
    path: list[str] = []

    def visit(name: str, referrer: tuple[str, str] | None = None) -> None:
        if name in path:
            raise CycleError(" -> ".join([*path[path.index(name) :], name]))
        if name in classes:
            return
        try:
            cls = replacements[name] if name in replacements else registry.get(name)
        except UnknownNodeError as exc:
            if referrer is None:
                raise
            arg, owner = referrer
            raise UnknownNodeError(f"{exc} (input {arg!r} of {owner!r})") from None
        path.append(name)
        for arg, dep in cls.all_inputs().items():
            visit(dep, (arg, name))
        path.pop()
        classes[name] = cls

    for target in targets:
        visit(target)
    return classes


def _topological_names(classes: Mapping[str, type[Node]]) -> list[str]:
    """Kahn's algorithm over node names; ties broken by name."""
    deps = {n: set(c.all_inputs().values()) for n, c in classes.items()}
    ready = [n for n, d in deps.items() if not d]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for other, d in deps.items():
            if name in d:
                d.remove(name)
                if not d:
                    heapq.heappush(ready, other)
    return order


def _instantiate(
    classes: Mapping[str, type[Node]], node_params: Mapping[str, Mapping[str, Any]]
) -> dict[str, Node]:
    """Build one instance per class from its params; ParamsError on bad or stray params."""
    stray = sorted(set(node_params) - set(classes))
    if stray:
        raise ParamsError(f"params given for nodes not in the graph: {stray}")
    instances: dict[str, Node] = {}
    for name, cls in classes.items():
        try:
            instances[name] = cls.model_validate(node_params.get(name, {}))
        except ValidationError as exc:
            raise ParamsError(f"invalid params for node {name!r}: {exc}") from exc
    return instances


def build_plan(
    targets: Sequence[str],
    registry: "NodeRegistry",
    candidates: Sequence[CandidateRef],
    *,
    node_params: Mapping[str, Mapping[str, Any]] | None = None,
    replacements: Mapping[str, type[Node]] | None = None,
    run_id: str | None = None,
) -> ExecutionPlan:
    """Resolve `targets` into an ExecutionPlan expanded over `candidates`.

    Shared nodes get one key, candidate nodes one per candidate. `plan.nodes` is in
    deterministic topological order. Raises a GraphError subclass on any invalid input.
    """
    ids = [c.id for c in candidates]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise DuplicateCandidateError(f"duplicate candidate ids: {dupes}")

    classes = resolve_classes(targets, registry, replacements)
    for rule in GRAPH_RULES:
        rule(classes)
    instances = _instantiate(classes, node_params or {})
    for name, instance in instances.items():
        instance.bind_upstream({arg: classes[up].contract() for arg, up in classes[name].all_inputs().items()})

    def keys_for(name: str) -> list[NodeKey]:
        if classes[name].scope == "shared":
            return [NodeKey(name=name, candidate=None)]
        return [NodeKey(name=name, candidate=c.id) for c in candidates]

    nodes: dict[NodeKey, PlannedNode] = {}
    for name in _topological_names(classes):
        cls = classes[name]
        for key in keys_for(name):
            deps = {
                arg: NodeKey(
                    name=up, candidate=None if classes[up].scope == "shared" else key.candidate
                )
                for arg, up in cls.all_inputs().items()
            }
            nodes[key] = PlannedNode(
                key=key, node=instances[name], deps=deps, optional=frozenset(cls.optional_inputs)
            )
    if run_id is None:
        run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    return ExecutionPlan(run_id=run_id, candidates=list(candidates), nodes=nodes)


def to_mermaid(classes: Mapping[str, type[Node]]) -> str:
    """Render the node-level graph as a Mermaid flowchart (`-.->` marks optional edges)."""
    lines = ["flowchart LR"]
    for name, cls in classes.items():
        lines.append(f"    {name}:::shared" if cls.scope == "shared" else f"    {name}")
        for up in cls.inputs.values():
            lines.append(f"    {up} --> {name}")
        for up in cls.optional_inputs.values():
            lines.append(f"    {up} -.-> {name}")
    lines.append("    classDef shared stroke-dasharray: 4 2")
    return "\n".join(lines)
