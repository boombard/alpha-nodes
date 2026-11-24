"""lensgraph: generic candidates x lenses -> dossiers core (no domain concepts)."""

from .aggregate import Aggregator, ShrunkMeanAggregator, VetoAggregator
from .citations import citable_ids
from .config import ReportOptions, RunConfig, Settings, load_object
from .graph import build_plan
from .lens import DepthRequirement, LensAssessment, LensNode, input_sufficiency
from .node import CalcNode, FetchNode, Node, TransformNode
from .panel import Panel, dossiers, panel_registry
from .records import DossierRecord, LLMCall
from .registry import NodeRegistry
from .run import RunSpec, arun, run
from .types import Absent, CandidateRef, GlobalFailure
from .verdict import (
    AssessmentBrief,
    Claim,
    Dossier,
    DossierReview,
    Flag,
    LensVerdict,
    Provenance,
    ReviewPoint,
)

__all__ = [
    "Absent",
    "Aggregator",
    "AssessmentBrief",
    "CalcNode",
    "CandidateRef",
    "Claim",
    "DepthRequirement",
    "Dossier",
    "DossierRecord",
    "DossierReview",
    "FetchNode",
    "Flag",
    "GlobalFailure",
    "LLMCall",
    "LensAssessment",
    "LensNode",
    "LensVerdict",
    "Node",
    "NodeRegistry",
    "Panel",
    "Provenance",
    "ReportOptions",
    "ReviewPoint",
    "RunConfig",
    "RunSpec",
    "Settings",
    "ShrunkMeanAggregator",
    "TransformNode",
    "VetoAggregator",
    "arun",
    "build_plan",
    "citable_ids",
    "dossiers",
    "input_sufficiency",
    "load_object",
    "panel_registry",
    "run",
]
