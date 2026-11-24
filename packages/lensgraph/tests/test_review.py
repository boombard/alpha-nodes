"""DossierReviewer: citables, guard rails, brief handling, caching and panel wiring."""

from typing import Any

import pytest
from lensgraph import AssessmentBrief, Dossier, DossierReview, Panel, RunSpec, run
from lensgraph.aggregate import ShrunkMeanAggregator
from lensgraph.llm import LLMProfile, ProfileRegistry
from lensgraph.node import NodeContext
from lensgraph.panel import panel_registry
from lensgraph.plan import NodeKey
from lensgraph.review import render_review_context, review_citables
from lensgraph.types import CandidateRef
from lensgraph.verdict import Claim, Flag, LensVerdict, Provenance
from pydantic_ai.exceptions import UnexpectedModelBehavior
from toy.registry import build_registry, build_services
from toy.reviewer import ToyReviewer

BRIEF = AssessmentBrief(purpose="Pick strains for a pilot", priorities=["speed", "safety"])
GOOD: dict[str, Any] = {
    "summary": "Fast and safe.",
    "fit": [{"text": "fast", "cites": ["verdict.growth"], "priority": "speed"}],
    "gaps": [{"text": "no tox data", "cites": ["verdict.safety.claim[0]"]}],
    "flags": [],
}


def _verdict(lens: str, status: str = "ok") -> LensVerdict:
    ok = status == "ok"
    return LensVerdict(
        lens=lens,
        status=status,  # type: ignore[arg-type]
        stance=1 if ok else None,
        conviction="high" if ok else None,
        stance_mean=1.0 if ok else None,
        coverage=1.0 if ok else 0.0,
        claims=[Claim(text="a", direction=1, cites=["x"]), Claim(text="b", direction=-1, cites=["y"])]
        if ok
        else [],
        flags=[Flag(severity="warn", code="tox_signal", text="t", cites=["x"])] if ok else [],
        error=None if ok else "boom",
        provenance=Provenance(lens_version="v"),
    )


@pytest.fixture
def dossier() -> Dossier:
    return ShrunkMeanAggregator().combine(
        CandidateRef(id="S1"), [_verdict("growth"), _verdict("safety")]
    )


@pytest.fixture
def ctx(scripted_profiles) -> Any:
    def make(*payloads: dict[str, Any]) -> NodeContext:
        return NodeContext(
            run_id="r",
            candidate=CandidateRef(id="S1"),
            services={"profiles": scripted_profiles(*payloads)},
            input_hashes={"dossier": "h"},
        )

    return make


def _review(ctx_, dossier, brief: AssessmentBrief | None = BRIEF, **params) -> DossierReview:
    import asyncio

    node = ToyReviewer(brief=brief, profile="test", **params)
    return asyncio.run(node.run(ctx_, dossier=dossier))


def test_review_citables_from_dossier(dossier):
    assert review_citables(dossier) == {
        "verdict.growth",
        "verdict.growth.claim[0]",
        "verdict.growth.claim[1]",
        "flag.growth.tox_signal",
        "verdict.safety",
        "verdict.safety.claim[0]",
        "verdict.safety.claim[1]",
        "flag.safety.tox_signal",
    }


def test_review_ok_becomes_dossier_review_with_provenance(ctx, dossier):
    review = _review(ctx(GOOD), dossier)
    assert review.summary == "Fast and safe."
    assert review.fit[0].priority == "speed"
    assert review.provenance.lens_version == ToyReviewer.code_version()
    assert review.provenance.input_hashes == {"dossier": "h"}
    assert review.provenance.prompt_hash and review.provenance.model
    assert review.provenance.attempts == 1


def test_unknown_cite_retried_then_ok(scripted_profiles, dossier):
    bad = {**GOOD, "fit": [{"text": "x", "cites": ["verdict.nope"]}]}
    profiles = scripted_profiles(bad, GOOD)
    context = NodeContext(run_id="r", candidate=None, services={"profiles": profiles})
    review = _review(context, dossier)
    assert review.provenance.attempts == 2


def test_unknown_flag_code_rejected(ctx, dossier):
    bad = {**GOOD, "flags": [{"severity": "warn", "code": "made_up", "text": "t"}]}
    with pytest.raises(UnexpectedModelBehavior):
        _review(ctx(bad), dossier)


def test_unknown_priority_retried(ctx, dossier):
    bad = {**GOOD, "fit": [{"text": "x", "cites": ["verdict.growth"], "priority": "cost"}]}
    with pytest.raises(UnexpectedModelBehavior, match="priority"):
        _review(ctx(bad), dossier)


def test_fit_without_brief_rejected(ctx, dossier):
    with pytest.raises(UnexpectedModelBehavior, match="no brief"):
        _review(ctx(GOOD), dossier, brief=None)


def test_no_brief_summary_only_ok(ctx, dossier):
    review = _review(ctx({**GOOD, "fit": []}), dossier, brief=None)
    assert review.fit == []


def test_show_stances_false_hides_stances(dossier):
    shown = render_review_context(dossier)
    hidden = render_review_context(dossier, show_stances=False)
    assert "stance" in shown
    assert "stance" not in hidden and "direction" not in hidden
    assert "claim[0]" in hidden and "tox_signal" in hidden and "coverage" in hidden


def test_brief_in_system_prompt_dossier_in_user_message(scripted_model, dossier):
    model = scripted_model(GOOD)
    profiles = ProfileRegistry(
        {"test": LLMProfile(name="test", model="test")}, model_overrides={"test": model}
    )
    context = NodeContext(run_id="r", candidate=None, services={"profiles": profiles})
    _review(context, dossier)
    from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

    parts = [p for m in model.calls[0] if isinstance(m, ModelRequest) for p in m.parts]
    system = next(str(p.content) for p in parts if isinstance(p, SystemPromptPart))
    user = next(str(p.content) for p in parts if isinstance(p, UserPromptPart))
    assert "Pick strains for a pilot" in system and "Pick strains" not in user
    assert "verdict.growth" in user


def test_no_stance_or_score_in_output_schema():
    assert {"stance", "score", "overall_stance"}.isdisjoint(DossierReview.model_fields)


PANEL = Panel(lenses=["growth_lens", "safety_lens"], reviewer="toy_reviewer")


@pytest.fixture
def wired():
    return panel_registry(PANEL, build_registry())


def _run_panel(wired, candidates, tmp_path, brief: dict[str, Any] | None) -> Any:
    spec = RunSpec(
        panel=PANEL,
        candidates=candidates,
        targets=PANEL.targets(),
        nodes={
            "safety_lens": {"profile": "test"},
            "review": {"profile": "test", "brief": brief},
        },
    )
    return run(spec, wired, store_root=tmp_path, services=build_services())


def test_reviewer_wired_by_panel(wired, toy_candidates, tmp_path):
    assert PANEL.targets() == ["dossier", "review"]
    result = _run_panel(wired, toy_candidates, tmp_path, BRIEF.model_dump())
    for cand in ("S1", "S2", "S3"):
        review = result.values[NodeKey(name="review", candidate=cand)]
        assert isinstance(review, DossierReview)


def test_brief_change_invalidates_review_only(wired, toy_candidates, tmp_path):
    s1 = toy_candidates[:1]
    _run_panel(wired, s1, tmp_path, BRIEF.model_dump())
    second = _run_panel(wired, s1, tmp_path, {**BRIEF.model_dump(), "purpose": "Another aim"})
    hit = {k.name: r.cache_hit for k, r in second.results.items() if r.status == "ok"}
    assert hit["review"] is False
    assert hit["dossier"] and hit["growth_lens"] and hit["safety_lens"]


def test_panel_without_reviewer_has_only_aggregator_target():
    assert Panel(lenses=["a"]).targets() == ["dossier"]


def test_panel_reviewer_must_be_a_dossier_reviewer():
    from lensgraph.graph import GraphError

    panel = Panel(lenses=["growth_lens", "safety_lens"], reviewer="growth_lens")
    with pytest.raises(GraphError, match="growth_lens.*GrowthLens"):
        panel_registry(panel, build_registry())
