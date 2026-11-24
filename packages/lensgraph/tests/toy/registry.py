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
from .safety_lens import SafetyLens
from .sources import FakeAssaySource

_SAFE = {
    "status": "ok",
    "stance": 1,
    "conviction": "high",
    "claims": [{"text": "grows", "direction": 1, "cites": ["growth_rate"]}],
    "flags": [],
}


def build_registry(lenses: tuple[type[Node], ...] = (GrowthLens, SafetyLens)) -> NodeRegistry:
    """Registry with every toy data node plus `lenses` (default: `GrowthLens` and the AI `SafetyLens`).

    Tests that register lenses themselves pass fewer.
    """
    registry = NodeRegistry()
    for cls in (ReferencePanel, AssayRaw, AssayClean, GrowthRate, ToxNotes, *lenses):
        registry.register(cls)
    return registry


def _scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Always answer with the canned safe assessment, in whichever output mode is asked for."""
    if info.output_tools:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, _SAFE)])
    return ModelResponse(parts=[TextPart(json.dumps(_SAFE))])


def build_services() -> dict[str, Any]:
    """Services for an offline toy run: the fake assay source and a scripted `test` profile."""
    profiles = ProfileRegistry(
        {"test": LLMProfile(name="test", model="test")},
        model_overrides={"test": FunctionModel(_scripted)},
    )
    return {"assays": FakeAssaySource(), "profiles": profiles}
