"""Verdict model validators."""

import pytest
from lensgraph.verdict import Claim, LensVerdict, Provenance
from pydantic import ValidationError


def _verdict(**kw) -> LensVerdict:
    base = {"lens": "l", "status": "ok", "coverage": 1.0, "provenance": Provenance(lens_version="v")}
    return LensVerdict(**{**base, **kw})


def test_verdict_ok_requires_stance_and_conviction():
    with pytest.raises(ValidationError):
        _verdict(status="ok")
    with pytest.raises(ValidationError):
        _verdict(status="ok", stance=1)
    with pytest.raises(ValidationError):  # stance_mean is required too
        _verdict(status="ok", stance=1, conviction="low")
    assert _verdict(status="ok", stance=1, conviction="low", stance_mean=1.0).stance == 1


def test_verdict_failed_has_no_stance():
    with pytest.raises(ValidationError):
        _verdict(status="failed", stance=1, conviction="low")
    assert _verdict(status="failed", coverage=0.0).stance is None


def test_claim_requires_a_cite():
    with pytest.raises(ValidationError):
        Claim(text="t", direction=1, cites=[])


@pytest.mark.parametrize("field", ["stance_mean", "stance_spread"])
@pytest.mark.parametrize("status", ["abstained", "failed"])
def test_verdict_non_ok_has_no_stance_mean_or_spread(status, field):
    with pytest.raises(ValidationError):
        _verdict(status=status, coverage=0.0, **{field: 0.5})


def test_stance_mean_bounded_and_spread_non_negative():
    ok = {"status": "ok", "stance": 2, "conviction": "high"}
    with pytest.raises(ValidationError):
        _verdict(**ok, stance_mean=2.5)
    with pytest.raises(ValidationError):
        _verdict(**ok, stance_mean=1.6, stance_spread=-0.1)
    assert _verdict(**ok, stance_mean=1.6, stance_spread=0.49).stance_spread == 0.49
