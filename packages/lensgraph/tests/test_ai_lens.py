"""AINode: prompt assembly, the citation guard rail, retries, memoization and provenance."""

import shutil
from pathlib import Path
from typing import Any, ClassVar

import pytest
from lensgraph import RunSpec, run
from lensgraph.ai import AIAssessmentOut
from lensgraph.glossary import Glossary, GlossaryError
from lensgraph.llm import DEFAULT_PROFILES
from lensgraph.plan import NodeKey, RunResult
from lensgraph.verdict import LensVerdict
from pydantic_ai.messages import ModelRequest, SystemPromptPart, ToolReturnPart, UserPromptPart
from toy.registry import build_registry
from toy.safety_lens import SafetyLens

GOOD: dict[str, Any] = {
    "status": "ok",
    "stance": 1,
    "conviction": "medium",
    "claims": [
        {"text": "grows steadily", "direction": 1, "cites": ["growth_rate", "tox_notes[S1-n1]"]}
    ],
    "flags": [],
}


def _with(**changes: Any) -> dict[str, Any]:
    return {**GOOD, **changes}


def _bad_cite(cite: str) -> dict[str, Any]:
    return _with(claims=[{"text": "x", "direction": 1, "cites": [cite]}])


def _run(registry, candidates, services, profiles, tmp_path, **node_params) -> RunResult:
    spec = RunSpec(
        targets=["safety_lens"],
        candidates=candidates,
        nodes={"safety_lens": {"profile": "test", **node_params}},
    )
    return run(spec, registry, store_root=tmp_path, services={**services, "profiles": profiles})


def _key(candidate: str, name: str = "safety_lens") -> NodeKey:
    return NodeKey(name=name, candidate=candidate)


def _text_parts(messages, part_type) -> list[str]:
    return [
        str(p.content)  # pyright: ignore[reportAttributeAccessIssue]
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, part_type)
    ]


@pytest.fixture
def s1(toy_candidates):
    return toy_candidates[:1]


def test_ok_answer_becomes_verdict_with_provenance(
    ai_registry, s1, toy_services, scripted_profiles, tmp_path
):
    profiles = scripted_profiles(GOOD, settings={"thinking": "low"})
    result = _run(ai_registry, s1, toy_services, profiles, tmp_path)
    verdict = result.values[_key("S1")]
    assert isinstance(verdict, LensVerdict) and verdict.status == "ok"
    assert (verdict.stance, verdict.conviction, verdict.stance_mean) == (1, "medium", 1.0)
    assert verdict.stance_spread is None
    prov = verdict.provenance
    assert prov.model  # the model label is recorded
    assert prov.model_settings == {"thinking": "low"}
    assert prov.variant == "default" and prov.prompt_hash
    assert prov.attempts == 1
    assert prov.input_tokens > 0 and prov.output_tokens > 0


def test_system_prompt_is_static_and_user_prompt_carries_context(
    ai_registry, s1, toy_services, scripted_profiles, tmp_path
):
    profiles = scripted_profiles(GOOD)
    _run(ai_registry, s1, toy_services, profiles, tmp_path)
    messages = profiles.model_for("test").calls[0]
    system = "\n".join(_text_parts(messages, SystemPromptPart))
    user = "\n".join(_text_parts(messages, UserPromptPart))
    assert "tox_signal" in system and "safety" in system
    assert "S1" not in system  # candidate-specific content stays out of the cacheable prefix
    assert "### [growth_rate]" in user and "### [tox_notes[S1-n1]]" in user
    assert "tox_notes: 1 of 3 desired items" in user


def test_first_answer_bad_citation_retried_then_ok(
    ai_registry, s1, toy_services, scripted_profiles, tmp_path
):
    profiles = scripted_profiles(_bad_cite("made_up"), GOOD)
    result = _run(ai_registry, s1, toy_services, profiles, tmp_path)
    verdict = result.values[_key("S1")]
    assert verdict.provenance.attempts == 2
    valid = {"growth_rate", "tox_notes", "tox_notes[S1-n1]"}
    assert {c for claim in verdict.claims for c in claim.cites} <= valid


def test_retries_exhausted_fails_node(ai_registry, toy_candidates, toy_services, scripted_profiles, tmp_path):
    profiles = scripted_profiles(_bad_cite("made_up"))
    result = _run(ai_registry, toy_candidates[:1], toy_services, profiles, tmp_path)
    node_result = result.results[_key("S1")]
    assert result.status == "ok"  # the run completes; the failure is data
    assert node_result.status == "failed"
    assert node_result.error is not None and "citation" in node_result.error.lower()


def test_citation_case_variant_rejected(ai_registry, s1, toy_services, scripted_profiles, tmp_path):
    profiles = scripted_profiles(_bad_cite("Growth_Rate"), GOOD)
    result = _run(ai_registry, s1, toy_services, profiles, tmp_path)
    assert result.values[_key("S1")].provenance.attempts == 2
    retry_text = "\n".join(_text_parts(profiles.model_for("test").calls[1], ToolReturnPart))
    assert "Unknown citation ids: ['Growth_Rate']" in retry_text
    assert "Valid ids:" in retry_text and "growth_rate" in retry_text


def test_unknown_flag_code_rejected(ai_registry, s1, toy_services, scripted_profiles, tmp_path):
    bad_flag = _with(flags=[{"severity": "warn", "code": "bogus", "text": "t", "cites": []}])
    ok_flag = _with(flags=[{"severity": "warn", "code": "tox_signal", "text": "t", "cites": ["growth_rate"]}])
    profiles = scripted_profiles(bad_flag, ok_flag)
    result = _run(ai_registry, s1, toy_services, profiles, tmp_path)
    verdict = result.values[_key("S1")]
    assert verdict.provenance.attempts == 2
    assert [f.code for f in verdict.flags] == ["tox_signal"]


def test_ok_without_stance_or_conviction_retried(
    ai_registry, s1, toy_services, scripted_profiles, tmp_path
):
    profiles = scripted_profiles(_with(stance=None), _with(conviction=None), GOOD)
    result = _run(ai_registry, s1, toy_services, profiles, tmp_path)
    assert result.values[_key("S1")].provenance.attempts == 3


def test_claim_without_cites_retried(ai_registry, s1, toy_services, scripted_profiles, tmp_path):
    no_cites = _with(claims=[{"text": "x", "direction": 1, "cites": []}])
    result = _run(ai_registry, s1, toy_services, scripted_profiles(no_cites, GOOD), tmp_path)
    assert result.values[_key("S1")].provenance.attempts == 2


def test_abstain_allowed_maps_to_abstained_verdict(
    ai_registry, s1, toy_services, scripted_profiles, tmp_path
):
    abstain = {"status": "abstained", "abstain_reason": "too little evidence"}
    result = _run(ai_registry, s1, toy_services, scripted_profiles(abstain), tmp_path)
    verdict = result.values[_key("S1")]
    assert verdict.status == "abstained" and verdict.error == "too little evidence"
    assert verdict.stance is None and verdict.provenance.attempts == 1


def test_absent_optional_input_rendered_not_available_and_not_citable(
    ai_registry, toy_candidates, toy_services, scripted_profiles, tmp_path
):
    s2 = toy_candidates[1:2]  # S2 has no tox notes
    cites_empty = _bad_cite("tox_notes")
    cites_ok = _with(claims=[{"text": "x", "direction": 1, "cites": ["growth_rate"]}])
    profiles = scripted_profiles(cites_empty, cites_ok)
    result = _run(ai_registry, s2, toy_services, profiles, tmp_path, critical_inputs=[])
    verdict = result.values[_key("S2")]
    assert verdict.provenance.attempts == 2  # citing the unavailable input was rejected
    assert verdict.coverage < 1
    user = "\n".join(_text_parts(profiles.model_for("test").calls[0], UserPromptPart))
    assert "tox_notes: NOT AVAILABLE" in user


def test_profile_change_invalidates_ai_memo_only(
    ai_registry, s1, toy_services, scripted_profiles, tmp_path
):
    _run(ai_registry, s1, toy_services, scripted_profiles(GOOD, settings={"a": 1}), tmp_path)
    again = _run(ai_registry, s1, toy_services, scripted_profiles(GOOD, settings={"a": 1}), tmp_path)
    assert again.results[_key("S1")].cache_hit
    changed = _run(ai_registry, s1, toy_services, scripted_profiles(GOOD, settings={"a": 2}), tmp_path)
    assert not changed.results[_key("S1")].cache_hit
    assert changed.results[_key("S1", "growth_rate")].cache_hit


def test_variant_changes_prompt_hash(ai_registry, s1, toy_services, scripted_profiles, tmp_path):
    default = _run(ai_registry, s1, toy_services, scripted_profiles(GOOD), tmp_path)
    strict = _run(ai_registry, s1, toy_services, scripted_profiles(GOOD), tmp_path, variant="strict")
    d, s = default.values[_key("S1")].provenance, strict.values[_key("S1")].provenance
    assert (d.variant, s.variant) == ("default", "strict")
    assert d.prompt_hash != s.prompt_hash
    assert not strict.results[_key("S1")].cache_hit


def test_prompted_output_mode_works(ai_registry, s1, toy_services, scripted_profiles, tmp_path):
    profiles = scripted_profiles(GOOD, output_mode="prompted")
    result = _run(ai_registry, s1, toy_services, profiles, tmp_path)
    assert result.values[_key("S1")].status == "ok"


def test_no_real_model_requests_allowed(
    ai_registry, s1, toy_services, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    spec = RunSpec(targets=["safety_lens"], candidates=s1)  # default `dev` profile, no override
    result = run(spec, ai_registry, store_root=tmp_path, services=toy_services)
    node_result = result.results[_key("S1")]
    assert node_result.status == "failed"
    assert node_result.error is not None and "not allowed" in node_result.error.lower()


def test_output_schema_is_subset_of_verdict():
    assert set(AIAssessmentOut.model_fields) == {
        "status", "stance", "conviction", "claims", "flags", "abstain_reason"
    }


def test_unknown_variant_rejected_at_build_plan(ai_registry, s1):
    from lensgraph.graph import ParamsError, build_plan

    with pytest.raises(ParamsError, match="safety_lens"):
        build_plan(["safety_lens"], ai_registry, s1, node_params={"safety_lens": {"variant": "strcit"}})
    build_plan(["safety_lens"], ai_registry, s1, node_params={"safety_lens": {"variant": "strict"}})


def test_request_limit_below_retries_fails_node_with_usage_limit_error(
    ai_registry, s1, toy_services, scripted_profiles, tmp_path
):
    from lensgraph.llm import UsageCaps

    profiles = scripted_profiles(
        _bad_cite("made_up"), max_retries=5, usage_limits=UsageCaps(request_limit=2)
    )
    result = _run(ai_registry, s1, toy_services, profiles, tmp_path)
    node_result = result.results[_key("S1")]
    assert result.status == "ok"
    assert node_result.status == "failed"
    assert node_result.error is not None and "request_limit" in node_result.error
    assert len(profiles.model_for("test").calls) == 2  # stopped by the ceiling, not retries


def test_ai_lens_abstains_without_model_call(ai_registry, toy_candidates, toy_services, tmp_path):
    from lensgraph.llm import LLMProfile, ProfileRegistry
    from pydantic_ai.models.function import FunctionModel

    def boom(messages, info):
        pytest.fail("model must not be called when a critical input is absent")

    profile = LLMProfile(name="test", model="test")
    profiles = ProfileRegistry({"test": profile}, model_overrides={"test": FunctionModel(boom)})
    result = _run(ai_registry, toy_candidates[1:2], toy_services, profiles, tmp_path)  # S2: no tox notes
    verdict = result.values[_key("S2")]
    assert isinstance(verdict, LensVerdict)
    assert verdict.status == "abstained"
    assert verdict.error == "critical input 'tox_notes' unavailable"
    assert verdict.provenance.model is None


TOY_GLOSSARY = Path(__file__).parent / "toy" / "glossary"


@pytest.fixture
def glossary_registry(tmp_path):
    """Factory: registry whose AI lens declares the term `growth-rate` of a toy glossary copy.

    `edit(entry, old, new)` rewrites one entry of the copy first (the lens then sees the edit).
    """

    def make(edit: tuple[str, str, str] | None = None):
        directory = tmp_path / f"glossary-{len(list(tmp_path.glob('glossary-*')))}"
        shutil.copytree(TOY_GLOSSARY, directory)
        if edit:
            path = directory / f"{edit[0]}.md"
            path.write_text(path.read_text().replace(edit[1], edit[2], 1))

        class GlossarySafety(SafetyLens):
            """SafetyLens with a toy glossary."""

            glossary: ClassVar[Glossary | None] = Glossary.load(directory)
            glossary_terms: ClassVar[frozenset[str]] = frozenset({"growth-rate"})

        return build_registry(lenses=(GlossarySafety,))

    return make


def _system(profiles) -> str:
    return "\n".join(_text_parts(profiles.model_for("test").calls[0], SystemPromptPart))


def test_glossary_off_by_default_on_dev(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    assert [DEFAULT_PROFILES[n].glossary for n in ("dev", "quality", "local")] == [False, False, True]
    profiles = scripted_profiles(GOOD)
    result = _run(glossary_registry(), s1, toy_services, profiles, tmp_path)
    assert "## Terms" not in _system(profiles)
    assert result.values[_key("S1")].provenance.glossary_terms == []


def test_profile_glossary_on_adds_block_after_static_prompt(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    profiles = scripted_profiles(GOOD, glossary=True)
    _run(glossary_registry(), s1, toy_services, profiles, tmp_path)
    system = _system(profiles)
    assert system.index("Raise flags only") < system.index("## Terms")
    assert "**Growth rate (GR)**: A per-hour fractional growth." in system
    assert "Doubling time" not in system and "Toxicity note" not in system  # undeclared terms


def test_node_param_overrides_profile(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    on = scripted_profiles(GOOD, glossary=True)
    _run(glossary_registry(), s1, toy_services, on, tmp_path, use_glossary=False)
    assert "## Terms" not in _system(on)
    off = scripted_profiles(GOOD)
    _run(glossary_registry(), s1, toy_services, off, tmp_path, use_glossary=True)
    assert "## Terms" in _system(off)


def test_glossary_edit_changes_prompt_hash_and_memo_salt(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    kwargs = {"use_glossary": True}
    first = _run(glossary_registry(), s1, toy_services, scripted_profiles(GOOD), tmp_path, **kwargs)
    edited = ("growth-rate", "Larger means faster", "Bigger means quicker")
    second = _run(
        glossary_registry(edited), s1, toy_services, scripted_profiles(GOOD), tmp_path, **kwargs
    )
    assert not second.results[_key("S1")].cache_hit
    assert (
        first.values[_key("S1")].provenance.prompt_hash
        != second.values[_key("S1")].provenance.prompt_hash
    )


def test_unused_entry_edit_does_not_change_hash(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    kwargs = {"use_glossary": True}
    first = _run(glossary_registry(), s1, toy_services, scripted_profiles(GOOD), tmp_path, **kwargs)
    edited = ("toxicity-note", "Weigh the wording", "Judge the wording")
    second = _run(
        glossary_registry(edited), s1, toy_services, scripted_profiles(GOOD), tmp_path, **kwargs
    )
    assert second.results[_key("S1")].cache_hit
    assert (
        first.values[_key("S1")].provenance.prompt_hash
        == second.values[_key("S1")].provenance.prompt_hash
    )


def test_unknown_glossary_term_rejected_at_class_definition():
    with pytest.raises(GlossaryError, match="nope"):

        class Bad(SafetyLens):
            """Declares a term the glossary lacks."""

            glossary: ClassVar[Glossary | None] = Glossary.load(TOY_GLOSSARY)
            glossary_terms: ClassVar[frozenset[str]] = frozenset({"nope"})


def test_provenance_records_glossary_terms(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    result = _run(
        glossary_registry(), s1, toy_services, scripted_profiles(GOOD, glossary=True), tmp_path
    )
    assert result.values[_key("S1")].provenance.glossary_terms == ["growth-rate"]
