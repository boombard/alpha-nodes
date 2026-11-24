"""Factories for the toy domain, referenced by `toy_run.yaml` and shared with conftest."""

import json
from typing import Any

from lensgraph.llm import LLMProfile, ProfileRegistry
from lensgraph.node import Node
from lensgraph.registry import NodeRegistry
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .growth_lens import GrowthLens
from .nodes import AssayClean, AssayRaw, GrowthRate, ReferencePanel, ToxNotes
from .reviewer import toy_reviewer
from .safety_lens import SafetyLens
from .sources import FakeAssaySource

_SAFE = {
    "status": "ok",
    "stance": 1,
    "conviction": "high",
    "claims": [{"text": "grows", "direction": 1, "cites": ["growth_rate"]}],
    "flags": [],
}
_REVIEW = {
    "summary": "Grows well; safety evidence is thin.",
    "fit": [{"text": "grows quickly", "cites": ["verdict.growth"], "priority": "speed"}],
    "gaps": [],
    "flags": [],
}
_REVIEW_FAILED = {"summary": "No lens produced a verdict.", "fit": [], "gaps": [], "flags": []}


def build_registry(lenses: tuple[type[Node], ...] = (GrowthLens, SafetyLens)) -> NodeRegistry:
    """Registry with every toy data node plus `lenses` (default: `GrowthLens` and the AI `SafetyLens`).

    Tests that register lenses themselves pass fewer.
    """
    registry = NodeRegistry()
    for cls in (ReferencePanel, AssayRaw, AssayClean, GrowthRate, ToxNotes, toy_reviewer, *lenses):
        registry.register(cls)
    return registry


def _scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Answer with a canned payload chosen by the output schema: review or safety assessment.

    The reviewer's schema has a `summary` property; the review is also made to cite only
    ids that exist in the prompt it was shown (so a dossier with no ok verdicts gets a
    review without claim cites).
    """
    schema = info.output_tools[0].parameters_json_schema if info.output_tools else {}
    if "summary" in schema.get("properties", {}):
        prompt = "".join(str(getattr(p, "content", "")) for m in messages for p in m.parts)
        payload = _REVIEW if "### [verdict.growth]" in prompt else _REVIEW_FAILED
    else:
        payload = _SAFE
    if info.output_tools:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])
    return ModelResponse(parts=[TextPart(json.dumps(payload))])


def build_services() -> dict[str, Any]:
    """Services for an offline toy run: the fake assay source and scripted `test`/`test2` profiles.

The scripted model answers both the safety lens and the reviewer, by output schema.
"""
    profiles = ProfileRegistry(
        {
            "test": LLMProfile(name="test", model="test"),
            # Same scripted answers, different settings: a distinct fingerprint, so switching
            # a run to it (`lensgraph run --profile test2`) re-keys the AI nodes.
            "test2": LLMProfile(name="test2", model="test", settings={"temperature": 0.1}),
        },
        model_overrides={"test": FunctionModel(_scripted), "test2": FunctionModel(_scripted)},
    )
    return {"assays": FakeAssaySource(), "profiles": profiles}
