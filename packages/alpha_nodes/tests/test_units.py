import pytest
from alpha_nodes.units import is_major_iso, to_major


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("GBp", ("GBP", 100)),
        ("GBX", ("GBP", 100)),
        ("ZAc", ("ZAR", 100)),
        ("ILA", ("ILS", 100)),
        ("EUR", ("EUR", 1)),
    ],
)
def test_to_major_minor_units(code: str, expected: tuple[str, int]) -> None:
    assert to_major(code) == expected


@pytest.mark.parametrize("junk", ["", "gbp", "EURO", "E1R", "US"])
def test_to_major_rejects_junk(junk: str) -> None:
    with pytest.raises(ValueError):
        to_major(junk)


@pytest.mark.parametrize(
    ("code", "ok"),
    [
        ("GBP", True),
        ("EUR", True),
        ("GBp", False),
        ("GBX", False),
        ("ILA", False),
        ("gbp", False),
        ("EU", False),
        ("", False),
    ],
)
def test_is_major_iso(code: str, ok: bool) -> None:
    assert is_major_iso(code) is ok
