"""Field kinds, minor-unit currency handling and ISO currency checks.

Canonical datasets store money in major units only; providers normalise with `to_major`.
See documentation/design/finance.md, Currency.
"""

import re
from typing import Literal

FieldKind = Literal["money", "per_share", "shares", "ratio", "count", "date", "text", "code"]
"""What a canonical column means; every dataset column declares one via `metadata={"kind": ...}`."""

MINOR_UNITS: dict[str, tuple[str, int]] = {
    "GBp": ("GBP", 100),
    "GBX": ("GBP", 100),
    "ZAc": ("ZAR", 100),
    "ILA": ("ILS", 100),
}
"""Minor-unit currency code -> (major ISO code, minor units per major unit)."""

_ISO = re.compile(r"[A-Z]{3}")


def is_major_iso(code: str) -> bool:
    """True for three upper-case letters that are not a minor-unit code (e.g. not "GBX")."""
    return bool(_ISO.fullmatch(code)) and code not in MINOR_UNITS


def to_major(currency: str) -> tuple[str, int]:
    """Return (major ISO code, divisor) for a currency code; divisor is 100 for pence-like codes.

    Raises ValueError for anything that is neither a minor-unit code nor a major ISO shape.
    """
    if currency in MINOR_UNITS:
        return MINOR_UNITS[currency]
    if is_major_iso(currency):
        return currency, 1
    raise ValueError(f"not a currency code: {currency!r}")
