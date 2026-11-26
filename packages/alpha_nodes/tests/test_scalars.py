import math

import numpy as np
import pytest
from alpha_nodes.scalars import opt, ratio


@pytest.mark.parametrize(("value", "expected"), [(float("nan"), None), (1.5, 1.5), (0.0, 0.0), (np.float64(2.0), 2.0)])
def test_opt_maps_nan_to_none(value, expected):
    assert opt(value) == expected


def test_opt_returns_a_plain_float():
    assert type(opt(np.float64(2.0))) is float


@pytest.mark.parametrize(
    ("num", "den", "expected"),
    [(1.0, 2.0, 0.5), (None, 2.0, None), (1.0, None, None), (1.0, 0.0, None), (1.0, -2.0, None), (-1.0, 2.0, -0.5)],
)
def test_ratio_is_none_unless_denominator_positive(num, den, expected):
    got = ratio(num, den)
    assert got == expected
    assert got is None or not math.isnan(got)
