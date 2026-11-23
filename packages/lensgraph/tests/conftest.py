"""Shared fixtures: the toy strain domain (S1 fine, S2 no tox notes, S3 missing od600)."""

import json
from collections.abc import Callable
from typing import Any

import pydantic_ai.models
import pytest
from lensgraph.llm import LLMProfile, ProfileRegistry
from lensgraph.registry import NodeRegistry
from lensgraph.types import CandidateRef
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from toy.nodes import AssayClean, AssayRaw, GrowthRate, ReferencePanel, ToxNotes
from toy.safety_lens import SafetyLens
from toy.sources import FakeAssaySource


@pytest.fixture(autouse=True)
def _forbid_real_model_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may reach a real model; only FunctionModel/TestModel instances can answer."""
    monkeypatch.setattr(pydantic_ai.models, "ALLOW_MODEL_REQUESTS", False)


class ScriptedModel(FunctionModel):
    """A `FunctionModel` that replays canned answers and records every request it received."""

    def __init__(self, payloads: tuple[dict[str, Any], ...]) -> None:
        self.calls: list[list[ModelMessage]] = []
        self._payloads = payloads
        super().__init__(self._answer)

    def _answer(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        payload = self._payloads[min(len(self.calls), len(self._payloads) - 1)]
        self.calls.append(messages)
        if info.output_tools:  # tool output mode
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])
        return ModelResponse(parts=[TextPart(json.dumps(payload))])  # prompted/native mode


@pytest.fixture
def scripted_model() -> Callable[..., ScriptedModel]:
    """Factory: `scripted_model(p1, p2, ...)` answers call i with payload i (last one repeats).

    Each payload is a dict shaped like `AIAssessmentOut`.
    """
    return lambda *payloads: ScriptedModel(payloads)


@pytest.fixture
def scripted_profiles(scripted_model: Callable[..., ScriptedModel]) -> Callable[..., ProfileRegistry]:
    """Factory: registry whose `test` profile is backed by a scripted model."""

    def make(*payloads: dict[str, Any], **profile_kwargs: Any) -> ProfileRegistry:
        profile = LLMProfile(name="test", model="test", **profile_kwargs)
        return ProfileRegistry(
            {"test": profile}, model_overrides={"test": scripted_model(*payloads)}
        )

    return make


@pytest.fixture
def toy_source() -> FakeAssaySource:
    return FakeAssaySource()


@pytest.fixture
def toy_candidates() -> list[CandidateRef]:
    return [CandidateRef(id=s) for s in ("S1", "S2", "S3")]


@pytest.fixture
def toy_services(toy_source: FakeAssaySource) -> dict[str, FakeAssaySource]:
    return {"assays": toy_source}


@pytest.fixture
def toy_registry() -> NodeRegistry:
    """Registry holding every toy node."""
    registry = NodeRegistry()
    for cls in (ReferencePanel, AssayRaw, AssayClean, GrowthRate, ToxNotes):
        registry.register(cls)
    return registry


@pytest.fixture
def ai_registry(toy_registry: NodeRegistry) -> NodeRegistry:
    """Toy registry plus the AI `SafetyLens`."""
    toy_registry.register(SafetyLens)
    return toy_registry
