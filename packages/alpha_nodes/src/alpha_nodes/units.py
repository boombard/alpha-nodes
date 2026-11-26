"""Finance units, minor-unit currency handling and ISO currency checks.

The finance `Unit` values (money prefixed from a currency field, per-share money, shares) that
canonical datasets and result models declare; generic units come from `lensgraph.units`.
Canonical datasets store money in major units only; providers normalise with `to_major`.
See documentation/design/finance.md, Units and currency are data, and Currency.
"""

import re

from lensgraph.units import Unit

MONEY = Unit(id="money", style="compact", prefix_field="currency")
"""An amount of money (statement line items, market cap), prefixed by the sibling `currency` field."""

MONEY_PER_SHARE = Unit(id="money_per_share", style="number", decimals=2, prefix_field="currency")
"""A per-share amount (price, dividend), prefixed by the sibling `currency` field."""

TRADING_MONEY_PER_SHARE = Unit(id="trading_money_per_share", style="number", decimals=2, prefix_field="trading_currency")
"""A per-share amount in the trading currency, for results whose `currency` is the reporting one."""

SHARES = Unit(id="shares", style="compact", suffix=" shares")
"""A share count."""

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
