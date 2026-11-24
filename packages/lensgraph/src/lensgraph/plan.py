"""Execution plan (what to run) and result (what happened) models.

The plan is built from nodes and candidates and consumed by an executor; see
documentation/design/core.md, Graph and Execution.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .node import Node
from .types import CandidateRef, Failed


class NodeKey(BaseModel):
    """Identity of one node instance in a plan: node name plus candidate id (None if shared)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    candidate: str | None

    def __str__(self) -> str:
        return self.name if self.candidate is None else f"{self.name}[{self.candidate}]"


class PlannedNode(BaseModel):
    """A node instance placed in the plan with its dependencies resolved to NodeKeys."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    key: NodeKey
    node: Node
    deps: dict[str, NodeKey]  # run() kwarg name -> producing node instance
    optional: frozenset[str]  # kwarg names in `deps` that are optional (failure -> Absent)


class ExecutionPlan(BaseModel):
    """A resolved DAG of node instances for one run; an executor walks it in order."""

    model_config = ConfigDict(extra="forbid")
    run_id: str
    candidates: list[CandidateRef]
    nodes: dict[NodeKey, PlannedNode]  # insertion order is topological

    def descendants(self, names: set[str]) -> set[NodeKey]:
        """Keys of the named nodes plus everything downstream of them."""
        found: set[NodeKey] = set()
        for key, planned in self.nodes.items():
            if key.name in names or any(dep in found for dep in planned.deps.values()):
                found.add(key)
        return found


NodeStatus = Literal["ok", "failed", "skipped", "recovered"]
"""ok; failed (raised); skipped (upstream failed); recovered (on_upstream_failure handled it)."""


class NodeResult(BaseModel):
    """Outcome of one node instance, recorded in the run index (the audit trail)."""

    model_config = ConfigDict(extra="forbid")
    key: NodeKey
    status: NodeStatus
    output_hash: str | None = None  # content hash of the stored output; None if no output
    memo_key: str | None = None  # see hashing.memo_key; None for non-memoized nodes
    cache_hit: bool = False  # True if the output came from the memo cache, not run()
    error: str | None = None
    failure: Failed | None = None
    duration_s: float = 0.0
    meta: dict[str, Any] = {}  # free-form extras (e.g. token usage for AI nodes)


class RunResult(BaseModel):
    """Outcome of a whole run: per-node results plus, in memory only, the output values."""

    model_config = ConfigDict(extra="forbid")
    run_id: str
    status: Literal["ok", "aborted"]  # aborted: a GlobalFailure stopped the run
    results: dict[NodeKey, NodeResult]
    values: dict[NodeKey, Any] = Field(default_factory=dict, exclude=True)  # not serialized

