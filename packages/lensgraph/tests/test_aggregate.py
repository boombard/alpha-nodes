"""Aggregator.combine (pure) and the Aggregator node's handling of absent lens inputs."""

from typing import Any, ClassVar

import pytest
from lensgraph.aggregate import Aggregator, ShrunkMeanAggregator, VetoAggregator
from lensgraph.node import NodeContext
from lensgraph.types import Absent, CandidateRef
from lensgraph.verdict import Flag, LensVerdict, Provenance

CAND = CandidateRef(id="C1")


def verdict(
    lens: str,
    stance: Any = None,
    coverage: float = 1.0,
    conviction: Any = "high",
    status: Any = "ok",
    flags: Any = (),
) -> LensVerdict:
    """Build a verdict; ok ones get `stance_mean == stance`."""
    ok = status == "ok"
    return LensVerdict(
        lens=lens,
        status=status,
        stance=stance if ok else None,
        conviction=conviction if ok else None,
        stance_mean=float(stance or 0) if ok else None,
        coverage=coverage,
        flags=list(flags),
        error=None if ok else "x",
        provenance=Provenance(lens_version="v"),
    )


def veto(code="bad"):
    return Flag(severity="veto", code=code, text="t")


def test_combine_worked_example():
    a = verdict("a", 2, 1.0, "high")
    b = verdict("b", -1, 0.5, "medium")
    d = ShrunkMeanAggregator().combine(CAND, [a, b])
    assert d.weights == {"a": 1.0, "b": 0.375}
    assert d.direction == pytest.approx(1.181818, rel=1e-5)
    assert d.evidence_share == d.confidence == pytest.approx(0.6875)
    assert d.overall_stance == pytest.approx(0.8125)
    assert d.agreement == pytest.approx(1.336085, rel=1e-5)
    assert d.coverage == {"a": "ok", "b": "ok"}


def test_all_failed_or_abstained():
    d = ShrunkMeanAggregator().combine(
        CAND, [verdict("a", status="failed"), verdict("b", status="abstained")]
    )
    assert d.overall_stance is None and d.confidence == 0.0 and d.agreement is None
    assert d.direction is None and d.evidence_share == 0.0
    assert d.weights == {"a": 0.0, "b": 0.0}
    assert d.coverage == {"a": "failed", "b": "abstained"}


def test_single_ok_verdict_agreement_none():
    d = ShrunkMeanAggregator().combine(CAND, [verdict("a", 1), verdict("b", status="failed")])
    assert d.agreement is None and d.overall_stance == pytest.approx(0.5)  # 1.0 direction x 0.5 share


def test_lens_weight_param_changes_result():
    vs = [verdict("a", 2), verdict("b", -2)]
    even = ShrunkMeanAggregator().combine(CAND, vs).overall_stance
    heavy = ShrunkMeanAggregator(lens_weights={"a": 3.0}).combine(CAND, vs).overall_stance
    assert even == pytest.approx(0.0) and heavy is not None and heavy > 0.5


def test_veto_forces_minus_two():
    vs = [verdict("a", 2, flags=[veto()]), verdict("b", 2)]
    assert VetoAggregator().combine(CAND, vs).overall_stance == -2.0
    assert ShrunkMeanAggregator().combine(CAND, vs).overall_stance != -2.0


def test_veto_codes_restrict_which_flags_qualify():
    vs = [verdict("a", 2, flags=[veto("other")])]
    assert VetoAggregator(veto_codes=["bad"]).combine(CAND, vs).overall_stance != -2.0
    assert VetoAggregator(veto_codes=["other"]).combine(CAND, vs).overall_stance == -2.0


def test_flags_are_unioned():
    f = Flag(severity="warn", code="w", text="t")
    d = ShrunkMeanAggregator().combine(CAND, [verdict("a", 1, flags=[f]), verdict("b", 1, flags=[veto()])])
    assert [x.code for x in d.flags] == ["w", "bad"]


def test_absent_lens_input_becomes_failed_verdict():
    class Agg(ShrunkMeanAggregator):
        optional_inputs: ClassVar[dict[str, str]] = {"a": "a", "b": "b"}

    ctx = NodeContext(run_id="r", candidate=CAND)
    d = Agg().run(ctx, a=verdict("a", 1), b=Absent(reason="upstream 'b' failed: boom"))
    bad = next(v for v in d.verdicts if v.lens == "b")
    assert bad.status == "failed" and bad.error == "upstream 'b' failed: boom"
    assert d.coverage == {"a": "ok", "b": "failed"} and d.weights["b"] == 0.0
    assert d.candidate == CAND


def test_thin_coverage_lowers_confidence():
    full = ShrunkMeanAggregator().combine(CAND, [verdict("a", 2, 1.0)])
    thin = ShrunkMeanAggregator().combine(CAND, [verdict("a", 2, 0.5)])
    assert thin.confidence < full.confidence
    assert thin.overall_stance is not None and full.overall_stance is not None
    assert abs(thin.overall_stance) < abs(full.overall_stance)


def test_aggregator_is_a_verdict_consumer():
    assert Aggregator.consumes_verdicts and Aggregator.name == "dossier"


def test_absent_lens_uses_lens_name_key():
    class Agg(ShrunkMeanAggregator):
        optional_inputs: ClassVar[dict[str, str]] = {"growth_lens": "growth_lens"}
        lens_names: ClassVar[dict[str, str]] = {"growth_lens": "growth"}

    ctx = NodeContext(run_id="r", candidate=CAND)
    d = Agg(lens_weights={"growth": 2.0}).run(ctx, growth_lens=Absent(reason="boom"))
    assert d.coverage == {"growth": "failed"} and d.weights == {"growth": 0.0}


def test_perfect_small_panel_not_shrunk():
    d = ShrunkMeanAggregator().combine(CAND, [verdict("a", 2), verdict("b", 2)])
    assert d.overall_stance == pytest.approx(2.0) and d.confidence == pytest.approx(1.0)


@pytest.mark.parametrize("n", [1, 2, 5])
def test_panel_size_independent(n):
    d = ShrunkMeanAggregator().combine(CAND, [verdict(f"l{i}", 1) for i in range(n)])
    assert d.overall_stance == pytest.approx(1.0)
