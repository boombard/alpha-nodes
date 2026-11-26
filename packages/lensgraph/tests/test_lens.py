"""LensNode template, coverage, citations and the lens dependency rule."""

import asyncio
import time
from typing import Any, ClassVar

import pytest
from lensgraph import RunSpec, run
from lensgraph.graph import GraphError, LensDependencyError, lens_dependency_rule
from lensgraph.lens import DepthRequirement, LensAssessment, LensNode, input_sufficiency
from lensgraph.node import CalcNode, NodeContext
from lensgraph.plan import NodeKey
from lensgraph.registry import NodeRegistry
from lensgraph.types import Absent, ContractViolation, Failed
from lensgraph.verdict import Claim, LensVerdict
from pydantic import ValidationError
from toy.nodes import ToxNote


@pytest.mark.parametrize(
    ("value", "req", "expected"),
    [
        ([1, 2, 3, 4], DepthRequirement(desired=8, minimum=3), 0.5),
        ([1, 2], DepthRequirement(desired=8, minimum=3), 0.0),
        (list(range(10)), DepthRequirement(desired=8, minimum=3), 1.0),
        (Absent(reason="x"), DepthRequirement(desired=8, minimum=3), 0.0),
        ([], DepthRequirement(desired=8, minimum=3), 0.0),
        (None, None, 0.0),
        ([1], None, 1.0),
    ],
)
def test_input_sufficiency(value, req, expected):
    assert input_sufficiency(value, req) == expected


def _ctx() -> NodeContext:
    return NodeContext(run_id="r", candidate=None, input_hashes={"a": "h"})


class WeightedLens(LensNode):
    name: ClassVar[str] = "weighted"
    lens_name: ClassVar[str] = "weighted"
    inputs: ClassVar[dict[str, str]] = {"a": "up_a", "b": "up_b"}
    input_weights: ClassVar[dict[str, float]] = {"a": 3.0}
    depth: ClassVar[dict[str, DepthRequirement]] = {"b": DepthRequirement(desired=2)}

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        return LensAssessment(status="ok", stance=1, conviction="low")


async def test_lens_coverage_weighted():
    verdict = await WeightedLens().run(_ctx(), a=[1], b=[])
    assert verdict.coverage == 0.75
    assert verdict.input_sufficiency == {"a": 1.0, "b": 0.0}
    assert verdict.provenance.input_hashes == {"a": "h"}
    assert verdict.lens == "weighted"


def test_lens_upstream_failure_verdict():
    failure = Failed(origin="assay_clean", candidate="S3", error="boom")
    verdict = WeightedLens().on_upstream_failure(_ctx(), failure)
    assert verdict.status == "failed"
    assert verdict.coverage == 0.0
    assert verdict.error is not None and "assay_clean" in verdict.error
    assert verdict.provenance.input_hashes == {}


class _Cites(LensNode):
    name: ClassVar[str] = "cites"
    lens_name: ClassVar[str] = "cites"
    inputs: ClassVar[dict[str, str]] = {"a": "up_a"}
    cite: str = "a"

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        return LensAssessment(
            status="ok",
            stance=1,
            conviction="low",
            claims=[Claim(text="t", direction=1, cites=[self.cite])],
        )


async def test_claim_citing_unknown_id_raises_contract_violation():
    assert (await _Cites().run(_ctx(), a=1.0)).claims[0].cites == ["a"]
    with pytest.raises(ContractViolation):
        await _Cites(cite="nope").run(_ctx(), a=1.0)


class _Abstains(LensNode):
    name: ClassVar[str] = "abstains"
    lens_name: ClassVar[str] = "abstains"
    inputs: ClassVar[dict[str, str]] = {"a": "up_a"}

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        return LensAssessment(status="abstained", abstain_reason="too thin", provenance_extra={"attempts": 2})


async def test_abstained_assessment_maps_reason_to_error():
    verdict = await _Abstains().run(_ctx(), a=1.0)
    assert verdict.status == "abstained"
    assert verdict.error == "too thin"
    assert verdict.stance is None
    assert verdict.provenance.attempts == 2


def _classes(**named: type) -> dict[str, type]:
    return dict(named)


class _Up(CalcNode):
    name: ClassVar[str] = "up"


class _LensA(LensNode):
    name: ClassVar[str] = "lens_a"
    lens_name: ClassVar[str] = "lens_a"
    inputs: ClassVar[dict[str, str]] = {"x": "up"}

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        return LensAssessment(status="abstained")


class _LensOnLens(CalcNode):
    name: ClassVar[str] = "lens_on_lens"
    inputs: ClassVar[dict[str, str]] = {"v": "lens_a"}


class _Aggregator(_LensOnLens):
    name: ClassVar[str] = "agg"
    consumes_verdicts: ClassVar[bool] = True


def test_lens_on_lens_rejected():
    with pytest.raises(LensDependencyError):
        lens_dependency_rule({"up": _Up, "lens_a": _LensA, "lens_on_lens": _LensOnLens})
    assert issubclass(LensDependencyError, GraphError)


def test_consumes_verdicts_allowed():
    lens_dependency_rule({"up": _Up, "lens_a": _LensA, "agg": _Aggregator})


class _ToyLens(LensNode):
    name: ClassVar[str] = "toy_lens"
    lens_name: ClassVar[str] = "toy_lens"
    inputs: ClassVar[dict[str, str]] = {"growth_rate": "growth_rate", "tox_notes": "tox_notes"}

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        notes: list[ToxNote] = inputs["tox_notes"]
        cites = ["growth_rate", *(f"tox_notes[{n.id}]" for n in notes[:1])]
        assert set(cites) <= citables
        positive = inputs["growth_rate"] > 0
        return LensAssessment(
            status="ok",
            stance=1 if positive else -1,
            conviction="medium",
            claims=[Claim(text="growth", direction=1 if positive else -1, cites=cites)],
        )


def test_toy_lens_runs_end_to_end(toy_registry: NodeRegistry, toy_candidates, toy_services, tmp_path):
    toy_registry.register(_ToyLens)
    spec = RunSpec(targets=["toy_lens"], candidates=toy_candidates)
    result = run(spec, toy_registry, store_root=tmp_path, services=toy_services)
    s1 = result.values[NodeKey(name="toy_lens", candidate="S1")]
    assert isinstance(s1, LensVerdict) and s1.status == "ok" and s1.coverage == 1.0
    s3 = result.results[NodeKey(name="toy_lens", candidate="S3")]
    assert s3.status == "recovered"
    failed = result.values[NodeKey(name="toy_lens", candidate="S3")]
    assert isinstance(failed, LensVerdict) and failed.status == "failed"


class _SlowSync(LensNode):
    name: ClassVar[str] = "slow_sync"
    lens_name: ClassVar[str] = "slow_sync"
    inputs: ClassVar[dict[str, str]] = {"a": "up_a"}

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        time.sleep(0.2)
        return LensAssessment(status="abstained")


async def test_sync_assess_runs_off_the_event_loop():
    start = time.perf_counter()
    await asyncio.gather(_SlowSync().run(_ctx(), a=[1]), _SlowSync().run(_ctx(), a=[1]))
    assert time.perf_counter() - start < 0.35


class _BadProvenance(LensNode):
    name: ClassVar[str] = "bad_prov"
    lens_name: ClassVar[str] = "bad_prov"
    inputs: ClassVar[dict[str, str]] = {"a": "up_a"}
    key: str = "lens_version"

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        return LensAssessment(status="abstained", provenance_extra={self.key: "x"})


@pytest.mark.parametrize("key", ["lens_version", "input_hashes"])
async def test_provenance_extra_cannot_override_template_fields(key):
    with pytest.raises(ContractViolation, match=f"bad_prov.*{key}"):
        await _BadProvenance(key=key).run(_ctx(), a=[1])


class _Stance(LensNode):
    name: ClassVar[str] = "stance_lens"
    lens_name: ClassVar[str] = "stance_lens"
    inputs: ClassVar[dict[str, str]] = {"a": "up_a"}
    assessment: dict[str, Any] = {}  # noqa: RUF012  (pydantic field, copied per instance)

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        return LensAssessment.model_validate(self.assessment)


async def test_template_fills_stance_mean_from_stance():
    lens = _Stance(assessment={"status": "ok", "stance": -2, "conviction": "low"})
    verdict = await lens.run(_ctx(), a=[1])
    assert verdict.stance_mean == -2.0
    assert verdict.stance_spread is None


async def test_template_passes_through_stance_mean_spread_and_samples():
    lens = _Stance(
        assessment={
            "status": "ok",
            "stance": -2,
            "conviction": "low",
            "stance_mean": -1.6,
            "stance_spread": 0.49,
            "provenance_extra": {"stance_samples": [-2, -2, -1, -2, -1]},
        }
    )
    verdict = await lens.run(_ctx(), a=[1])
    assert (verdict.stance_mean, verdict.stance_spread) == (-1.6, 0.49)
    assert verdict.provenance.stance_samples == [-2, -2, -1, -2, -1]


async def test_abstained_assessment_with_stance_mean_violates_contract():
    lens = _Stance(assessment={"status": "abstained", "abstain_reason": "x", "stance_mean": 0.5})
    with pytest.raises(ContractViolation, match="stance_lens"):
        await lens.run(_ctx(), a=[1])


class _Critical(LensNode):
    """Lens whose `assess` must never run when a threshold is unmet."""

    name: ClassVar[str] = "critical"
    lens_name: ClassVar[str] = "critical"
    inputs: ClassVar[dict[str, str]] = {"a": "up_a", "b": "up_b"}
    depth: ClassVar[dict[str, DepthRequirement]] = {"b": DepthRequirement(desired=4, minimum=2)}

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        return LensAssessment(status="ok", stance=1, conviction="low")


class _MustNotAssess(_Critical):
    name: ClassVar[str] = "must_not_assess"

    def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
        raise AssertionError("assess must not be called")


async def test_critical_input_absent_abstains_without_assess():
    lens = _MustNotAssess(critical_inputs=frozenset({"a"}))
    verdict = await lens.run(_ctx(), a=Absent(reason="x"), b=[1, 2, 3, 4])
    assert verdict.status == "abstained"
    assert verdict.error == "critical input 'a' unavailable"
    assert verdict.stance is None and verdict.conviction is None and verdict.claims == []
    assert verdict.input_sufficiency == {"a": 0.0, "b": 1.0}
    assert verdict.coverage == 0.5
    assert verdict.provenance.input_hashes == {"a": "h"}
    assert verdict.provenance.lens_version


async def test_critical_input_below_depth_minimum_abstains():
    lens = _MustNotAssess(critical_inputs=frozenset({"b"}))
    verdict = await lens.run(_ctx(), a=[1], b=[1])
    assert verdict.status == "abstained"
    assert verdict.error == "critical input 'b' unavailable"


async def test_several_critical_inputs_unavailable_counts_rest():
    lens = _MustNotAssess(critical_inputs=frozenset({"b", "a"}))
    verdict = await lens.run(_ctx(), a=None, b=[])
    assert verdict.error == "critical input 'a' unavailable (+1 more)"


async def test_min_coverage_abstains_with_reason():
    lens = _MustNotAssess(min_coverage=0.6)
    verdict = await lens.run(_ctx(), a=[1], b=[1])  # b below minimum -> coverage 0.5
    assert verdict.status == "abstained"
    assert verdict.error == "coverage 0.50 below minimum 0.60"
    assert verdict.coverage == 0.5


async def test_above_thresholds_judges_as_before():
    lens = _Critical(critical_inputs=frozenset({"a"}), min_coverage=0.5)
    verdict = await lens.run(_ctx(), a=[1], b=[1, 2, 3, 4])
    assert verdict.status == "ok" and verdict.stance == 1 and verdict.error is None


def test_unknown_critical_input_rejected():
    with pytest.raises(ValidationError, match=r"nope.*known.*\['a', 'b'\]"):
        _Critical(critical_inputs=frozenset({"nope"}))


def test_min_coverage_bounds():
    with pytest.raises(ValidationError):
        _Critical(min_coverage=1.5)


def test_critical_inputs_settable_per_run(toy_registry: NodeRegistry, toy_candidates, toy_services, tmp_path):
    toy_registry.register(_ToyLens)

    def memo_key(nodes):
        spec = RunSpec(targets=["toy_lens"], candidates=toy_candidates[:1], nodes=nodes)
        result = run(spec, toy_registry, store_root=tmp_path, services=toy_services)
        return result.results[NodeKey(name="toy_lens", candidate="S1")].memo_key

    base = memo_key({})
    assert memo_key({"toy_lens": {"critical_inputs": ["tox_notes"]}}) != base


def _lens_over(node_cls, *, require_units: bool = True):
    """A lens reading the `culture` input from `node_cls`, as a plan build binds it."""
    from lensgraph.types import CandidateRef

    class CultureLens(LensNode):
        name: ClassVar[str] = "culture_lens"
        lens_name: ClassVar[str] = "culture"
        inputs: ClassVar[dict[str, str]] = {"culture": "culture"}

        def assess(self, ctx, citables, **inputs: Any) -> LensAssessment:
            return LensAssessment(
                status="ok",
                stance=1,
                conviction="low",
                claims=[Claim(text="t", direction=1, cites=["culture.yield_frac", "culture.volume"])],
            )

    CultureLens.require_units = require_units
    registry = NodeRegistry()
    registry.register(node_cls)
    registry.register(CultureLens)
    plan_args = (["culture_lens"], registry, [CandidateRef(id="S1")])
    return CultureLens, registry, plan_args


def test_numeric_field_without_unit_fails_plan():
    from lensgraph.graph import build_plan
    from lensgraph.units import UnitError
    from toy.unit_models import BareCultureNode

    _, _, args = _lens_over(BareCultureNode)
    with pytest.raises(UnitError) as err:
        build_plan(*args[:3])
    message = str(err.value)
    assert "culture_lens" in message and "'culture'" in message and "'doubling'" in message
    assert "yield_frac" not in message  # the annotated field is fine


def test_bool_and_date_fields_need_no_unit():
    from lensgraph.graph import build_plan
    from toy.unit_models import CultureNode

    _, _, args = _lens_over(CultureNode)
    build_plan(*args[:3])  # Culture has bool and str fields without units


def test_require_units_false_skips_the_check():
    from lensgraph.graph import build_plan
    from toy.unit_models import BareCultureNode

    _, _, args = _lens_over(BareCultureNode, require_units=False)
    build_plan(*args[:3])


def _bound(node_cls):
    cls, _, _ = _lens_over(node_cls)
    lens = cls()
    lens.bind_upstream({"culture": node_cls.contract()})
    return lens


def test_provenance_records_cite_units():
    import asyncio

    from lensgraph.units import FRACTION
    from toy.unit_models import Culture, CultureNode

    lens = _bound(CultureNode)
    ctx = NodeContext(run_id="r", candidate=None, input_hashes={})
    verdict = asyncio.run(lens.run(ctx, culture=Culture(yield_frac=0.1)))
    assert set(verdict.provenance.cite_units) == {"culture.yield_frac", "culture.volume"}
    assert verdict.provenance.cite_units["culture.yield_frac"] == FRACTION
    # round-trips through JSON so the run view can read it from the index
    again = LensVerdict.model_validate_json(verdict.model_dump_json())
    assert again.provenance.cite_units == verdict.provenance.cite_units


def test_unit_change_changes_memo_salt():
    from lensgraph.units import Unit
    from toy.unit_models import CultureNode

    lens = _bound(CultureNode)
    before = lens.memo_salt({})
    lens._units = {**lens._units, "culture.yield_frac": Unit(id="fraction", style="number")}
    assert lens.memo_salt({}) != before


def test_unrelated_unit_change_keeps_memo_salt():
    from toy.unit_models import CultureNode

    lens = _bound(CultureNode)
    other = _bound(CultureNode)
    before = lens.memo_salt({})
    other._units = {**other._units, "elsewhere.x": next(iter(other._units.values()))}  # another lens's units
    assert lens.memo_salt({}) == before
    assert other.memo_salt({}) != before  # ... but a lens that sees them does change
