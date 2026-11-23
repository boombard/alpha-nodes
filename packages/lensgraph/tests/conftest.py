"""Shared fixtures: the toy strain domain (S1 fine, S2 no tox notes, S3 missing od600)."""

import pytest
from lensgraph.registry import NodeRegistry
from lensgraph.types import CandidateRef
from toy.nodes import AssayClean, AssayRaw, GrowthRate, ReferencePanel, ToxNotes
from toy.sources import FakeAssaySource


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
