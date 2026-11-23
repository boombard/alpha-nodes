"""lensgraph: generic candidates x lenses -> dossiers core (no domain concepts)."""

from .aggregate import Aggregator, ShrunkMeanAggregator, VetoAggregator
from .citations import citable_ids
from .graph import build_plan
from .lens import DepthRequirement, LensAssessment, LensNode, input_sufficiency
from .node import CalcNode, FetchNode, Node, TransformNode
from .panel import Panel, dossiers, panel_registry
from .registry import NodeRegistry
from .run import RunSpec, arun, run
from .types import Absent, CandidateRef, GlobalFailure
from .verdict import Claim, Dossier, Flag, LensVerdict, Provenance

__all__ = [
    "Absent",
    "Aggregator",
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
    "Panel",
    "Provenance",
    "RunSpec",
    "ShrunkMeanAggregator",
    "TransformNode",
    "VetoAggregator",
    "arun",
    "build_plan",
    "citable_ids",
    "dossiers",
    "input_sufficiency",
    "panel_registry",
    "run",
]
