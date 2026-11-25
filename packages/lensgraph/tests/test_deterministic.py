"""Deterministic lens: scorers, thresholds, conviction, stance_mean, missing components."""

import itertools
import math
from typing import Any, ClassVar

import numpy as np
import pytest
from lensgraph import RunSpec, run
from lensgraph.deterministic import Component, DeterministicLens, LinearScorer
from lensgraph.graph import ParamsError, build_plan
from lensgraph.node import NodeContext
from lensgraph.plan import NodeKey
from lensgraph.registry import NodeRegistry
from lensgraph.types import Absent
from lensgraph.verdict import LensVerdict
from pydantic import BaseModel
from toy.growth_lens import GrowthLens


class Pair(BaseModel):
    """Two-field input model for `<input>.<field>` sources."""

    a: float
    b: float | None = None


class DirectLens(DeterministicLens):
    """One component per field of a single `pair` input; unit scorers, so score = mean(a, b)."""

    name: ClassVar[str] = "direct"
    lens_name: ClassVar[str] = "direct"
    inputs: ClassVar[dict[str, str]] = {"pair": "pair_node"}
    components: ClassVar[list[Component]] = [
        Component(name="a", source="pair.a", scorer=LinearScorer(lo=-1, hi=1)),
        Component(name="b", source="pair.b", scorer=LinearScorer(lo=-1, hi=1), weight=3.0),
    ]


class ScoreLens(DeterministicLens):
    """Single component whose scorer is the identity on [-1, 1], to drive the score directly."""

    name: ClassVar[str] = "score_lens"
    lens_name: ClassVar[str] = "score_lens"
    inputs: ClassVar[dict[str, str]] = {"x": "x_node"}
    components: ClassVar[list[Component]] = [
        Component(name="x", source="x", scorer=LinearScorer(lo=-1, hi=1))
    ]


def _ctx() -> NodeContext:
    return NodeContext(run_id="r", candidate=None)


async def _verdict(lens, **inputs: Any) -> LensVerdict:
    return await lens.run(_ctx(), **inputs)


@pytest.mark.parametrize(("value", "expected"), [(0, -1), (0.5, 0), (1, 1), (2, 1), (-1, -1)])
def test_linear_scorer(value, expected):
    assert LinearScorer(lo=0, hi=1)(value) == expected


def test_linear_scorer_reversed():
    scorer = LinearScorer(lo=0, hi=1, higher_is_better=False)
    assert (scorer(0), scorer(1), scorer(0.5)) == (1, -1, 0)


@pytest.mark.parametrize(
    ("score", "stance"), [(-0.7, -2), (-0.3, -1), (0.0, 0), (0.3, 1), (0.7, 2)]
)
async def test_stance_thresholds(score, stance):
    verdict = await _verdict(ScoreLens(), x=score)
    assert verdict.stance == stance
    assert verdict.score == pytest.approx(score)


@pytest.mark.parametrize(("score", "conviction"), [(0.25, "low"), (0.45, "medium"), (0.95, "high")])
async def test_conviction_from_margin(score, conviction):
    assert (await _verdict(ScoreLens(), x=score)).conviction == conviction


@pytest.mark.parametrize(
    ("score", "mean", "stance"),
    [(0.19, 0.475, 0), (0.21, 0.525, 1), (0.75, 1.875, 2), (0.95, 2.0, 2), (0.0, 0.0, 0)],
)
async def test_stance_mean_interpolated(score, mean, stance):
    verdict = await _verdict(ScoreLens(), x=score)
    assert verdict.stance_mean == pytest.approx(mean)
    assert verdict.stance == stance
    assert verdict.stance_spread is None


async def test_stance_mean_monotone():
    means, mismatches = [], []
    for s in np.linspace(-1, 1, 201):
        verdict = await _verdict(ScoreLens(), x=float(s))
        assert verdict.stance_mean is not None
        means.append(verdict.stance_mean)
        on_tie = math.isclose(abs(verdict.stance_mean) % 1, 0.5)  # exactly on a threshold
        if not on_tie and round(verdict.stance_mean) != verdict.stance:
            mismatches.append(float(s))
    assert all(b >= a for a, b in itertools.pairwise(means))
    assert not mismatches


async def test_missing_component_skipped_and_weights_renormalised():
    full = await _verdict(DirectLens(), pair=Pair(a=0.2, b=0.6))
    assert full.score == pytest.approx((0.2 * 1 + 0.6 * 3) / 4)
    partial = await _verdict(DirectLens(), pair=Pair(a=0.2))
    assert partial.status == "ok"
    assert partial.components == {"a": pytest.approx(0.2)}
    assert partial.score == pytest.approx(0.2)
    assert [c.cites for c in partial.claims] == [["pair.a"]]


@pytest.mark.parametrize("value", [Absent(reason="x"), math.nan, math.inf])
async def test_unusable_values_skipped(value):
    verdict = await _verdict(ScoreLens(), x=value)
    assert verdict.status == "abstained"


async def test_all_components_missing_abstains():
    verdict = await _verdict(DirectLens(), pair=Absent(reason="gone"))
    assert verdict.status == "abstained"
    assert verdict.error == "no components available"
    assert verdict.stance is None and verdict.stance_mean is None
    assert verdict.score is None


async def test_weight_override_param(toy_candidates):
    plan = build_plan(
        ["direct"],
        _registry_with(DirectLens),
        toy_candidates[:1],
        node_params={"direct": {"weight_overrides": {"a": 3.0}}},
    )
    node = plan.nodes[NodeKey(name="direct", candidate="S1")].node
    verdict = await _verdict(node, pair=Pair(a=0.2, b=0.6))
    assert verdict.score == pytest.approx((0.2 * 3 + 0.6 * 3) / 6)


def _registry_with(lens: type[DeterministicLens]) -> NodeRegistry:
    from lensgraph.node import CalcNode

    class PairNode(CalcNode):
        name: ClassVar[str] = "pair_node"

    registry = NodeRegistry()
    registry.register(PairNode)
    registry.register(lens)
    return registry


async def test_claims_cite_component_source():
    verdict = await _verdict(DirectLens(), pair=Pair(a=0.5, b=-0.5))
    by_cite = {c.cites[0]: c for c in verdict.claims}
    assert set(by_cite) == {"pair.a", "pair.b"}
    assert by_cite["pair.a"].direction == 1 and by_cite["pair.b"].direction == -1
    assert by_cite["pair.a"].text == "a: 0.5"


def test_growth_lens_toy_run(toy_registry: NodeRegistry, toy_candidates, toy_services, tmp_path):
    toy_registry.register(GrowthLens)
    spec = RunSpec(targets=["growth_lens"], candidates=toy_candidates)
    result = run(spec, toy_registry, store_root=tmp_path, services=toy_services)
    for strain in ("S1", "S2"):
        verdict = result.values[NodeKey(name="growth_lens", candidate=strain)]
        assert isinstance(verdict, LensVerdict) and verdict.status == "ok"
        assert all(c.cites == ["growth_rate"] for c in verdict.claims) and verdict.claims
    failed = result.values[NodeKey(name="growth_lens", candidate="S3")]
    assert isinstance(failed, LensVerdict) and failed.status == "failed"


@pytest.mark.parametrize(
    "overrides", [{"grwoth": 2.0}, {"a": -1.0}], ids=["unknown_name", "negative_weight"]
)
def test_invalid_weight_overrides_rejected_at_plan_time(toy_candidates, overrides):
    with pytest.raises(ParamsError, match="direct"):
        build_plan(
            ["direct"],
            _registry_with(DirectLens),
            toy_candidates[:1],
            node_params={"direct": {"weight_overrides": overrides}},
        )


async def test_zero_total_weight_abstains():
    lens = DirectLens(weight_overrides={"a": 0.0, "b": 0.0})
    verdict = await _verdict(lens, pair=Pair(a=0.2, b=0.6))
    assert verdict.status == "abstained"
    assert verdict.error == "all available components have zero weight"


def test_linear_scorer_rejects_equal_bounds():
    with pytest.raises(ValueError, match="hi"):
        LinearScorer(lo=1, hi=1)


async def test_scorer_overrides_replace_default():
    base = await _verdict(ScoreLens(), x=0.5)
    override = LinearScorer(lo=0, hi=1)
    changed = await _verdict(ScoreLens(scorer_overrides={"x": override}), x=0.5)
    assert changed.components["x"] == pytest.approx(0.0)
    assert changed.components != base.components
    assert changed.score != base.score


def test_scorer_overrides_unknown_name_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match=r"known: \['a', 'b'\]"):
        DirectLens(scorer_overrides={"zzz": LinearScorer(lo=0, hi=1)})


class EvidenceLens(DeterministicLens):
    """One component with an extra `chart` evidence cite."""

    name: ClassVar[str] = "evidence_lens"
    lens_name: ClassVar[str] = "evidence_lens"
    inputs: ClassVar[dict[str, str]] = {"x": "x_node"}
    optional_inputs: ClassVar[dict[str, str]] = {"chart": "chart_node"}
    components: ClassVar[list[Component]] = [
        Component(
            name="x", source="x", scorer=LinearScorer(lo=-1, hi=1), evidence=("chart",)
        )
    ]


async def test_evidence_cited_when_available():
    verdict = await _verdict(EvidenceLens(), x=0.5, chart="a chart")
    assert verdict.claims[0].cites == ["x", "chart"]


async def test_evidence_skipped_when_not_citable():
    verdict = await _verdict(EvidenceLens(), x=0.5, chart=Absent(reason="none"))
    assert verdict.status == "ok"
    assert verdict.claims[0].cites == ["x"]
