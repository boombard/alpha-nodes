"""Currency helpers that refuse to mix currencies and never invent an fx rate.

Amounts in different currencies are never combined without an explicit fx factor; a missing
rate is `None`, never 1.0. See documentation/design/finance.md, Currency and Data quality principle 2.
"""

from datetime import date
from typing import Any, cast

import pandas as pd


class CurrencyMismatch(ValueError):
    """Amounts in different currencies were about to be combined."""


def require_same_currency(*codes: str) -> str:
    """Return the one currency code shared by all `codes`.

    Raises:
        CurrencyMismatch: naming every distinct code, when they differ.
    """
    distinct = sorted(set(codes))
    if len(distinct) != 1:
        raise CurrencyMismatch(f"mixed currencies without fx: {', '.join(distinct) or 'none given'}")
    return distinct[0]


def usd_per_unit(fx: pd.DataFrame, currency: str, on: date, *, max_stale_days: int = 7) -> float | None:
    """USD per one unit of `currency` on day `on`.

    Args:
        fx: frame as `FxRates` returns it: `entity` (the currency), `date`, `usd_per_unit`.
        max_stale_days: how old the last rate on or before `on` may be.

    Returns 1.0 for "USD" without reading `fx`; None when there is no rate on or before `on`
    within `max_stale_days`.
    """
    if currency == "USD":
        return 1.0
    if fx.empty:
        return None
    rows = fx[(fx["entity"] == currency) & (fx["date"] <= pd.Timestamp(on))]
    if rows.empty:
        return None
    last = cast(pd.DataFrame, rows).sort_values(by="date").iloc[-1]
    if (pd.Timestamp(on) - pd.Timestamp(cast(Any, last["date"]))).days > max_stale_days:
        return None
    return float(last["usd_per_unit"])


def fx_factor(fx: pd.DataFrame, from_ccy: str, to_ccy: str, on: date) -> float | None:
    """`to_ccy` units per one `from_ccy` unit on `on`, via USD; None when a rate is missing.

    Equal currencies give 1.0 without reading `fx`.
    """
    if from_ccy == to_ccy:
        return 1.0
    src, dst = usd_per_unit(fx, from_ccy, on), usd_per_unit(fx, to_ccy, on)
    if src is None or dst is None:
        return None
    return src / dst
