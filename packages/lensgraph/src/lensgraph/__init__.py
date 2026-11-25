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
from .review import DossierReviewer, ReviewOut, render_review_context, review_citables
from .run import RunSpec, arun, run
from .sources import (
    Clock,
    Dataset,
    DateInterval,
    FakeClock,
    IntervalSet,
    Provider,
    SourceSlice,
    SourceStore,
    SourceUnavailable,
    SystemClock,
)
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
from .view import RunView, build_run_view, write_run_view

__all__ = [
    "Absent",
    "Aggregator",
    "AssessmentBrief",
    "CalcNode",
    "CandidateRef",
    "Claim",
    "Clock",
    "Dataset",
    "DateInterval",
    "DepthRequirement",
    "Dossier",
    "DossierRecord",
    "DossierReview",
    "DossierReviewer",
    "FakeClock",
    "FetchNode",
    "Flag",
    "GlobalFailure",
    "IntervalSet",
    "LLMCall",
    "LensAssessment",
    "LensNode",
    "LensVerdict",
    "Node",
    "NodeRegistry",
    "Panel",
    "Provenance",
    "Provider",
    "ReportOptions",
    "ReviewOut",
    "ReviewPoint",
    "RunConfig",
    "RunSpec",
    "RunView",
    "Settings",
    "ShrunkMeanAggregator",
    "SourceSlice",
    "SourceStore",
    "SourceUnavailable",
    "SystemClock",
    "TransformNode",
    "VetoAggregator",
    "arun",
    "build_plan",
    "build_run_view",
    "citable_ids",
    "dossiers",
    "input_sufficiency",
    "load_object",
    "panel_registry",
    "render_review_context",
    "review_citables",
    "run",
    "write_run_view",
]
