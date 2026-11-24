"""Plan graph: the execution plan flattened to plain data (nodes with kinds, edges).

Persisted by the run index at run start for reports and live run views; see
documentation/design/core.md, Artifact store and run index. Lives apart from plan.py because
computing node kinds needs the lens and aggregator classes, which plan.py must not import.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .aggregate import Aggregator
from .lens import LensNode
from .node import CalcNode, FetchNode, Node, TransformNode
from .plan import ExecutionPlan, NodeKey
from .types import Scope

PlanNodeKind = Literal["fetch", "transform", "calc", "lens", "aggregator", "reviewer", "other"]
"""A node's base kind, for reports and run views. "reviewer" is reserved for the post-panel
reviewer node (M3.3); until it exists such nodes fall under "other"."""


def node_kind(node: Node) -> PlanNodeKind:
    """The base kind of `node`; the most specific base class wins ("other" if none matches)."""
    for cls, kind in (
        (Aggregator, "aggregator"),
        (LensNode, "lens"),
        (FetchNode, "fetch"),
        (TransformNode, "transform"),
        (CalcNode, "calc"),
    ):
        if isinstance(node, cls):
            return kind  # type: ignore[return-value]
    return "other"


class PlanNode(BaseModel):
    """One node instance in a `PlanGraph`: its key, scope and base kind."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    key: NodeKey
    scope: Scope
    kind: PlanNodeKind


class PlanEdge(BaseModel):
    """A dependency in a `PlanGraph`: `source`'s output feeds `target`'s `kwarg`."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    source: NodeKey
    target: NodeKey
    kwarg: str
    optional: bool


class PlanGraph(BaseModel):
    """The plan's DAG in plain data, persisted at run start for reports and live run views.

    See documentation/design/core.md, Artifact store and run index. Shared nodes appear once;
    `nodes` keeps the plan's topological order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    nodes: list[PlanNode]
    edges: list[PlanEdge]

    @classmethod
    def from_plan(cls, plan: ExecutionPlan) -> "PlanGraph":
        """Flatten `plan` into nodes (with kinds) and edges (with optionality)."""
        nodes = [
            PlanNode(key=key, scope=planned.node.scope, kind=node_kind(planned.node))
            for key, planned in plan.nodes.items()
        ]
        edges = [
            PlanEdge(source=dep, target=key, kwarg=kwarg, optional=kwarg in planned.optional)
            for key, planned in plan.nodes.items()
            for kwarg, dep in planned.deps.items()
        ]
        return cls(nodes=nodes, edges=edges)
