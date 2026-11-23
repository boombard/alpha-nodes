"""Toy panel (growth deterministic lens + safety AI lens) end to end through `run`."""

import json

import pytest
from lensgraph import RunSpec, run
from lensgraph.aggregate import VetoAggregator
from lensgraph.graph import ParamsError
from lensgraph.panel import Panel, dossiers, panel_registry
from lensgraph.plan import NodeKey
from toy.growth_lens import GrowthLens

GOOD = {
    "status": "ok",
    "stance": 1,
    "conviction": "high",
    "claims": [{"text": "grows", "direction": 1, "cites": ["growth_rate"]}],
    "flags": [],
}
PANEL = Panel(lenses=["growth_lens", "safety_lens"])


@pytest.fixture
def registry(ai_registry):
    ai_registry.register(GrowthLens)
    return panel_registry(PANEL, ai_registry)


def _run(registry, candidates, services, profiles, tmp_path, profile="test", **kw):
    spec = RunSpec(
        panel=PANEL,
        candidates=candidates,
        nodes={"safety_lens": {"profile": profile}},
        **kw,
    )
    return run(spec, registry, store_root=tmp_path, services={**services, "profiles": profiles})


def test_panel_e2e_toy(registry, toy_candidates, toy_services, scripted_profiles, tmp_path):
    result = _run(registry, toy_candidates, toy_services, scripted_profiles(GOOD), tmp_path)
    s1, s2, s3 = dossiers(result)
    assert [d.candidate.id for d in (s1, s2, s3)] == ["S1", "S2", "S3"]
    assert [v.status for v in s1.verdicts] == ["ok", "ok"] and s1.overall_stance is not None
    assert s2.coverage["safety"] == "ok"
    safety1 = next(v for v in s1.verdicts if v.lens == "safety")
    safety2 = next(v for v in s2.verdicts if v.lens == "safety")
    assert safety2.coverage < safety1.coverage < 1.000001
    assert s2.confidence < s1.confidence
    assert {v.status for v in s3.verdicts} == {"failed"}
    assert s3.overall_stance is None and s3.confidence == 0.0
    print(json.dumps([d.model_dump(mode="json") for d in (s1, s2, s3)], indent=2))


def test_panel_rerun_cached(registry, toy_candidates, toy_services, scripted_profiles, tmp_path):
    args = (registry, toy_candidates, toy_services, scripted_profiles(GOOD), tmp_path)
    _run(*args)
    second = _run(*args)
    memoizable = [r for r in second.results.values() if r.status == "ok" and r.memo_key is not None]
    assert any(k.name == "dossier" for k in second.results)
    assert memoizable and all(r.cache_hit for r in memoizable)


def test_profile_switch_reruns_only_ai_and_dossier(
    registry, toy_candidates, toy_services, scripted_profiles, tmp_path
):
    s1 = toy_candidates[:1]
    _run(registry, s1, toy_services, scripted_profiles(GOOD, settings={"a": 1}), tmp_path)
    second = _run(registry, s1, toy_services, scripted_profiles(GOOD, settings={"a": 2}), tmp_path)
    hit = {k.name: r.cache_hit for k, r in second.results.items() if r.status == "ok"}
    assert not hit["safety_lens"] and not hit["dossier"]
    assert hit["growth_lens"] and hit["growth_rate"] and hit["assay_clean"]


def test_custom_aggregator_class(
    ai_registry, toy_candidates, toy_services, scripted_profiles, tmp_path
):
    ai_registry.register(GrowthLens)
    reg = panel_registry(PANEL, ai_registry, aggregator_cls=VetoAggregator)
    result = _run(reg, toy_candidates[:1], toy_services, scripted_profiles(GOOD), tmp_path)
    assert isinstance(result.values[NodeKey(name="dossier", candidate="S1")].overall_stance, float)


def test_plain_registry_with_panel_spec_produces_dossiers(
    ai_registry, toy_candidates, toy_services, scripted_profiles, tmp_path
):
    ai_registry.register(GrowthLens)
    result = _run(ai_registry, toy_candidates, toy_services, scripted_profiles(GOOD), tmp_path)
    assert len(dossiers(result)) == 3


def test_failed_lens_keys_are_lens_names_for_every_candidate(
    registry, toy_candidates, toy_services, scripted_profiles, tmp_path
):
    result = _run(registry, toy_candidates, toy_services, scripted_profiles(GOOD), tmp_path)
    for d in dossiers(result):
        assert set(d.coverage) == set(d.weights) == {"growth", "safety"}


def test_empty_targets_without_panel_rejected(toy_registry, toy_candidates, tmp_path):
    with pytest.raises(ParamsError, match="targets or a panel"):
        run(RunSpec(candidates=toy_candidates), toy_registry, store_root=tmp_path)
