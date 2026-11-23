"""lensgraph: generic candidates x lenses -> dossiers core (no domain concepts)."""

from .citations import citable_ids
from .graph import build_plan
from .lens import DepthRequirement, LensAssessment, LensNode, input_sufficiency
from .node import CalcNode, FetchNode, Node, TransformNode
from .registry import NodeRegistry
from .run import RunSpec, arun, run
from .types import Absent, CandidateRef, GlobalFailure
from .verdict import Claim, Dossier, Flag, LensVerdict, Provenance

__all__ = [
    "Absent",
    "CalcNode",
    "CandidateRef",
    "Claim",
    "DepthRequirement",
    "Dossier",
    "FetchNode",
    "Flag",
    "GlobalFailure",
    "LensAssessment",
    "LensNode",
    "LensVerdict",
    "Node",
    "NodeRegistry",
    "Provenance",
    "RunSpec",
    "TransformNode",
    "arun",
    "build_plan",
    "citable_ids",
    "input_sufficiency",
    "run",
]
