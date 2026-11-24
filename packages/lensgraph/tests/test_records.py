"""Tests for the brief, review and record contracts and the new RunIndex methods."""

from datetime import UTC, datetime

import pytest
from lensgraph.plan import NodeKey, NodeResult
from lensgraph.records import DossierRecord, LLMCall
from lensgraph.store.memory import InMemoryRunIndex
from lensgraph.types import CandidateRef
from lensgraph.verdict import AssessmentBrief, Dossier, DossierReview, Provenance, ReviewPoint
from pydantic import ValidationError


def _review() -> DossierReview:
    return DossierReview(
        summary="s",
        fit=[ReviewPoint(text="fits", cites=["growth_rate"], priority="speed")],
        provenance=Provenance(lens_version="1"),
    )


def _dossier() -> Dossier:
    return Dossier(
        candidate=CandidateRef(id="S1"), verdicts=[], overall_stance=None, confidence=0.0,
        weights={}, agreement=None, coverage={}, flags=[],
    )


def test_brief_and_review_models_frozen_and_strict():
    brief = AssessmentBrief(purpose="p")
    assert brief.priorities == [] and brief.extra == {} and brief.horizon is None
    with pytest.raises(ValidationError):
        brief.purpose = "q"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="nope"):
        AssessmentBrief(purpose="p", nope=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        _review().summary = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="nope"):
        DossierReview(summary="s", provenance=Provenance(lens_version="1"), nope=1)  # type: ignore[call-arg]


def test_review_point_requires_cite():
    with pytest.raises(ValidationError):
        ReviewPoint(text="t", cites=[])


def test_dossier_record_roundtrip_json():
    rec = DossierRecord(
        run_id="r1", created_at=datetime(2026, 1, 1, tzinfo=UTC), dossier=_dossier(),
        review=_review(),
    )
    assert DossierRecord.model_validate_json(rec.model_dump_json()) == rec
    assert DossierRecord(run_id="r", created_at=rec.created_at, dossier=_dossier()).review is None


def test_memory_index_llm_calls_and_config():
    index = InMemoryRunIndex()
    index.start_run("r1", {"a": 1})
    calls = [
        LLMCall(run_id="r1", candidate="S1", node="safety_lens", model="m", attempts=1,
                input_tokens=10, output_tokens=5, cost_usd=0.01),
        LLMCall(run_id="r1", candidate=None, node="review", model="m", attempts=2,
                input_tokens=1, output_tokens=1, cost_usd=None),
    ]
    for call in calls:
        index.record_llm_call(call)
    assert index.llm_calls("r1") == calls and index.llm_calls("other") == []
    assert index.run_config("r1") == {"a": 1}
    result = NodeResult(key=NodeKey(name="n", candidate="S1"), status="ok", output_hash="h")
    index.record_node("r1", result)
    assert index.node_result("r1", "n", "S1") == result
    assert index.node_result("r1", "n", "S2") is None
    assert index.node_result("r1", "missing", None) is None
