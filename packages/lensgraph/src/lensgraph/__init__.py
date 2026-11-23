"""lensgraph: generic candidates x lenses -> dossiers core (no domain concepts)."""

from .graph import build_plan
from .node import CalcNode, FetchNode, Node, TransformNode
from .registry import NodeRegistry
from .run import RunSpec, arun, run
from .types import Absent, CandidateRef, GlobalFailure

__all__ = [
    "Absent",
    "CalcNode",
    "CandidateRef",
    "FetchNode",
    "GlobalFailure",
    "Node",
    "NodeRegistry",
    "RunSpec",
    "TransformNode",
    "arun",
    "build_plan",
    "run",
]
