"""Shared fixtures: the toy strain domain (S1 fine, S2 no tox notes, S3 missing od600)."""

import pytest
from lensgraph.types import CandidateRef
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
