"""AINode: prompt assembly, the citation guard rail, retries, memoization and provenance."""

import shutil
from pathlib import Path
from typing import Any, ClassVar

import pandera.pandas as pa
import pytest
from lensgraph import RunSpec, run
from lensgraph.ai import AIAssessmentOut, AINode
from lensgraph.glossary import GlossaryError
from lensgraph.graph import build_plan
from lensgraph.llm import DEFAULT_PROFILES, LLMProfile
from lensgraph.node import CalcNode, FetchNode, NodeContext
from lensgraph.plan import NodeKey, RunResult
from lensgraph.sources import DatasetFetch
from lensgraph.verdict import LensVerdict
from pandera.typing import Series
from pydantic import BaseModel
from pydantic_ai.messages import ModelRequest, SystemPromptPart, ToolReturnPart, UserPromptPart
from toy.nodes import ToxNote
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


class GrowthResult(BaseModel):
    """Output contract of the test calc node; the toy glossary claims both fields."""

    rate: float
    doubling_hours: float | None = None


class GrowthResultNode(CalcNode):
    """Test node producing a `GrowthResult` (a model contract, unlike the toy float)."""

    name: ClassVar[str] = "growth_result"
    output: ClassVar[Any] = GrowthResult

    def run(self, ctx: NodeContext) -> GrowthResult:
        return GrowthResult(rate=0.2, doubling_hours=3.5)


class TypedNotes(FetchNode):
    """Test node whose contract is `list[ToxNote]` (the item model carries the fields)."""

    name: ClassVar[str] = "typed_notes"
    output: ClassVar[Any] = list[ToxNote]

    def run(self, ctx: NodeContext) -> list[ToxNote]:
        return [ToxNote(id="n", text="t")]


class OtherResult(BaseModel):
    """A replacement contract with a field the toy glossary does not claim."""

    zzz: float


class OtherResultNode(GrowthResultNode):
    """Replacement of `growth_result` with a different contract."""

    output: ClassVar[Any] = OtherResult


class ObsFrame(pa.DataFrameModel):
    """Canonical columns of the toy observation dataset."""

    temp: Series[float]
    od: Series[float]


class ObsFetch(DatasetFetch):
    """Toy dataset fetch declaring its frame schema."""

    name: ClassVar[str] = "obs"
    dataset: ClassVar[str] = "obs"
    frame_schema: ClassVar = ObsFrame


class BareObsFetch(DatasetFetch):
    """Toy dataset fetch without a frame schema: contributes no fields."""

    name: ClassVar[str] = "obs"
    dataset: ClassVar[str] = "obs"


def _plan(registry, candidates, **kwargs):
    return build_plan(["safety_lens"], registry, candidates, node_params={"safety_lens": {"profile": "test"}}, **kwargs)


@pytest.fixture
def glossary_registry(tmp_path):
    """Factory: registry whose AI lens reads a `GrowthResult` input and has a toy glossary copy.

    `edit(entry, old, new)` rewrites one entry of the copy first. `optional` moves the result
    to an optional input; `concepts` sets `glossary_concepts`; `typed` adds a `list[ToxNote]` input;
    `critical` keeps the toy lens's critical `tox_notes` input.
    """

    def make(
        edit: tuple[str, str, str] | None = None,
        *,
        optional: bool = False,
        concepts: frozenset[str] = frozenset(),
        typed: bool = False,
        critical: bool = True,
        obs: type | None = None,
    ):
        directory = tmp_path / f"glossary-{len(list(tmp_path.glob('glossary-*')))}"
        shutil.copytree(TOY_GLOSSARY, directory)
        if edit:
            path = directory / f"{edit[0]}.md"
            path.write_text(path.read_text().replace(edit[1], edit[2], 1))
        required_in = {"growth_rate": "growth_rate"}
        optional_in = {"tox_notes": "tox_notes"}
        (optional_in if optional else required_in)["result"] = "growth_result"
        if typed:
            required_in["notes"] = "typed_notes"
        if obs is not None:
            required_in["observations"] = "obs"

        class GlossarySafety(SafetyLens):
            """SafetyLens with a toy glossary directory."""

            glossary: ClassVar[Path | None] = directory
            glossary_concepts: ClassVar[frozenset[str]] = concepts
            inputs: ClassVar[dict[str, str]] = required_in
            optional_inputs: ClassVar[dict[str, str]] = optional_in
            critical_inputs: frozenset[str] = frozenset({"tox_notes"}) if critical else frozenset()

        registry = build_registry(lenses=(GlossarySafety,))
        registry.register(GrowthResultNode)
        registry.register(TypedNotes)
        if obs is not None:
            registry.register(obs)
        return registry

    return make


def _system(profiles, call: int = 0) -> str:
    return "\n".join(_text_parts(profiles.model_for("test").calls[call], SystemPromptPart))


def test_dictionary_on_by_default_for_every_profile(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    assert all(not hasattr(p, "glossary") for p in DEFAULT_PROFILES.values())
    for kwargs in ({}, {"output_mode": "prompted"}, {"settings": {"thinking": "low"}}):
        profiles = scripted_profiles(GOOD, **kwargs)
        _run(glossary_registry(), s1, toy_services, profiles, tmp_path)
        system = _system(profiles)
        assert system.index("Raise flags only") < system.index("## Data dictionary")
        assert "- result.rate (ratio): **Growth rate (GR)**: A per-hour fractional growth." in system
        assert "result.doubling_hours (duration): **Doubling time**" in system
        assert "Toxicity note" not in system  # no input reaches it, not a declared concept


def test_profile_has_no_glossary_setting():
    assert "glossary" not in LLMProfile.model_fields


def test_uncovered_field_fails_plan_build(glossary_registry, s1):
    registry = glossary_registry(("growth-rate", "fields: [GrowthResult.rate]", "fields: []"))
    with pytest.raises(GlossaryError) as exc:
        _plan(registry, s1)
    message = str(exc.value)
    assert "safety_lens" in message and "'result'" in message and "'rate'" in message


def test_uncovered_field_fails_the_run_before_any_model_call(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    registry = glossary_registry(("growth-rate", "fields: [GrowthResult.rate]", "fields: []"))
    profiles = scripted_profiles(GOOD)
    with pytest.raises(GlossaryError):
        _run(registry, s1, toy_services, profiles, tmp_path)
    assert profiles.model_for("test").calls == []


def test_optional_input_fields_are_covered(glossary_registry, s1):
    registry = glossary_registry(("growth-rate", "fields: [GrowthResult.rate]", "fields: []"), optional=True)
    with pytest.raises(GlossaryError, match="rate"):
        _plan(registry, s1)


def test_list_of_models_contract_resolves_item_model(glossary_registry, s1):
    registry = glossary_registry(typed=True)
    with pytest.raises(GlossaryError, match=r"'notes'.*'id'"):  # ToxNote is unclaimed
        _plan(registry, s1)
    covered = glossary_registry(("toxicity-note", "fields: []", "fields: [ToxNote]"), typed=True)
    _plan(covered, s1)


def test_bare_contracts_contribute_no_fields(
    s1, toy_services, scripted_profiles, tmp_path
):
    class BareSafety(SafetyLens):
        """The toy lens: a float and a bare list input, so nothing needs a claim."""

        glossary: ClassVar[Path | None] = TOY_GLOSSARY

    profiles = scripted_profiles(GOOD)
    result = _run(build_registry(lenses=(BareSafety,)), s1, toy_services, profiles, tmp_path)
    assert "## Data dictionary" not in _system(profiles)
    assert result.values[_key("S1")].provenance.glossary_terms == []


def test_bind_uses_replacement_output(glossary_registry, s1):
    registry = glossary_registry()
    _plan(registry, s1)
    with pytest.raises(GlossaryError, match="zzz"):
        _plan(registry, s1, replacements={"growth_result": OtherResultNode})


def test_unknown_concept_fails_plan_build(glossary_registry, s1):
    with pytest.raises(GlossaryError, match=r"safety_lens.*nope"):
        _plan(glossary_registry(concepts=frozenset({"nope"})), s1)


def test_concept_ids_listed_without_paths(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    profiles = scripted_profiles(GOOD)
    registry = glossary_registry(concepts=frozenset({"toxicity-note"}))
    result = _run(registry, s1, toy_services, profiles, tmp_path)
    assert "- (count): **Toxicity note (TN)**: A single observation" in _system(profiles)
    assert result.values[_key("S1")].provenance.glossary_terms == [
        "doubling-time", "growth-rate", "toxicity-note",
    ]


def test_broken_entry_fails_only_plans_with_that_ai_lens(glossary_registry, s1):
    registry = glossary_registry(("growth-rate", "## Why it matters", "## Provider notes"))
    with pytest.raises(GlossaryError, match=r"growth-rate\.md"):
        _plan(registry, s1)
    build_plan(["growth_rate"], registry, s1)  # no AI lens: the glossary is never loaded


def test_use_glossary_false_omits_block_but_still_checks_coverage(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    profiles = scripted_profiles(GOOD)
    result = _run(glossary_registry(), s1, toy_services, profiles, tmp_path, use_glossary=False)
    assert "## Data dictionary" not in _system(profiles)
    assert result.values[_key("S1")].provenance.glossary_terms == []
    broken = glossary_registry(("growth-rate", "fields: [GrowthResult.rate]", "fields: []"))
    with pytest.raises(GlossaryError, match="rate"):
        _run(broken, s1, toy_services, scripted_profiles(GOOD), tmp_path, use_glossary=False)


def test_block_is_static_when_an_input_is_absent(
    glossary_registry, toy_candidates, toy_services, scripted_profiles, tmp_path
):
    profiles = scripted_profiles(GOOD)
    registry = glossary_registry(critical=False)
    _run(registry, toy_candidates[:2], toy_services, profiles, tmp_path)  # S2 has no tox notes
    systems = {_system(profiles, i) for i in range(len(profiles.model_for("test").calls))}
    assert len(systems) == 1 and "## Data dictionary" in systems.pop()


def test_used_note_edit_changes_memo_salt(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    first = _run(glossary_registry(), s1, toy_services, scripted_profiles(GOOD), tmp_path)
    edited = ("growth-rate", "Larger means faster", "Bigger means quicker")
    second = _run(glossary_registry(edited), s1, toy_services, scripted_profiles(GOOD), tmp_path)
    assert not second.results[_key("S1")].cache_hit
    assert (
        first.values[_key("S1")].provenance.prompt_hash
        != second.values[_key("S1")].provenance.prompt_hash
    )


def test_unused_section_edit_keeps_memo_salt(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    first = _run(glossary_registry(), s1, toy_services, scripted_profiles(GOOD), tmp_path)
    edited = ("doubling-time", "Only valid inside", "Only trustworthy inside")  # a used entry, other section
    second = _run(glossary_registry(edited), s1, toy_services, scripted_profiles(GOOD), tmp_path)
    assert second.results[_key("S1")].cache_hit
    assert (
        first.values[_key("S1")].provenance.prompt_hash
        == second.values[_key("S1")].provenance.prompt_hash
    )


def test_unused_entry_edit_keeps_memo_salt(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    _run(glossary_registry(), s1, toy_services, scripted_profiles(GOOD), tmp_path)
    edited = ("toxicity-note", "Weigh the wording", "Judge the wording")
    second = _run(glossary_registry(edited), s1, toy_services, scripted_profiles(GOOD), tmp_path)
    assert second.results[_key("S1")].cache_hit


def test_provenance_records_glossary_terms(
    glossary_registry, s1, toy_services, scripted_profiles, tmp_path
):
    result = _run(glossary_registry(), s1, toy_services, scripted_profiles(GOOD), tmp_path)
    assert result.values[_key("S1")].provenance.glossary_terms == ["doubling-time", "growth-rate"]


def test_unbound_ai_node_with_glossary_raises(glossary_registry, scripted_profiles):
    lens = glossary_registry().get("safety_lens")(profile="test")
    with pytest.raises(GlossaryError, match="not bound"):
        lens.memo_salt({"profiles": scripted_profiles(GOOD)})


def test_fetch_frame_schema_columns_reach_the_glossary_check(glossary_registry, s1):
    with pytest.raises(GlossaryError, match=r"'observations'.*'od'"):  # ObsFrame is unclaimed
        _plan(glossary_registry(obs=ObsFetch), s1)


def test_fetch_frame_schema_columns_appear_in_the_dictionary(glossary_registry, s1):
    registry = glossary_registry(("toxicity-note", "fields: []", "fields: [ObsFrame]"), obs=ObsFetch)
    plan = _plan(registry, s1)
    lens = next(p.node for k, p in plan.nodes.items() if k.name == "safety_lens")
    assert isinstance(lens, AINode)
    assert "observations.{od, temp}" in lens._system_prompt()


def test_fetch_without_frame_schema_contributes_nothing(glossary_registry, s1):
    _plan(glossary_registry(obs=BareObsFetch), s1)  # no error: no fields to claim
