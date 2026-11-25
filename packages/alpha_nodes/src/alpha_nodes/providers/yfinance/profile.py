"""yfinance profile payloads: the stored raw model, and its normalisation to `profile`.

See documentation/design/finance.md, "yfinance fetching and throttling" (Profile cost) and
"Data quality: yfinance quirks" (principles 1 and 2).
"""

import json
import re
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel

from alpha_nodes.units import to_major

PROFILE_NORMALISER_VERSION = "1"
"""Bump when `normalise_profile` changes behaviour; the store then renormalises."""


class YFProfilePayload(BaseModel):
    """The verbatim `Ticker.info` and ISIN for one symbol, JSON-safe; stored as the raw payload.

    Facts are rebuilt from this on renormalise (core.md, Source store).
    """

    symbol: str
    info: dict[str, Any]  # Ticker.info
    isin: str | None  # Ticker.isin; None when Yahoo returns "-" or nothing


def payload_from_ticker(symbol: str, info: dict[str, Any], isin: object) -> YFProfilePayload:
    """Capture `Ticker.info` and `Ticker.isin` as a `YFProfilePayload` (JSON-safe copy).

    Yahoo answers "-" (or nothing) when it has no ISIN; that becomes None.
    """
    return YFProfilePayload(
        symbol=symbol,
        info=json.loads(json.dumps(info, default=str)),
        isin=isin if isinstance(isin, str) and isin not in ("", "-") else None,
    )


def is_valid_isin(code: str) -> bool:
    """True for a well-formed ISIN: 2 letters, 9 alphanumerics, Luhn check digit (ISO 6166)."""
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", code):
        return False
    digits = "".join(str(int(c, 36)) for c in code)  # letters become 10..35
    total = 0
    for pos, ch in enumerate(reversed(digits)):
        d = int(ch)
        if pos % 2 == 1:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return total % 10 == 0


def _text(info: dict[str, Any], key: str) -> str | None:
    """A non-blank string field of `.info`, else None."""
    value = info.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _listing_date(info: dict[str, Any]) -> date | None:
    """First trade date (UTC day); None when Yahoo gave none."""
    millis = info.get("firstTradeDateMilliseconds")
    seconds = info.get("firstTradeDateEpochUtc")  # the name the design guessed; absent in 1.8.0
    if isinstance(millis, int | float):
        return datetime.fromtimestamp(millis / 1000, UTC).date()
    if isinstance(seconds, int | float):
        return datetime.fromtimestamp(seconds, UTC).date()
    return None


def normalise_profile(payload: YFProfilePayload, mic: str) -> pd.DataFrame:
    """Map a profile payload to one `ProfileSchema` row plus the `NormalisedMeta` columns.

    Only identity, listing facts, currencies and share count are taken; Yahoo's ratios and
    market cap are ignored (finance.md, principle 1). The trading currency is converted to
    its major unit (`minor_unit` repair). A missing or non-positive share count becomes NaN
    and the row `suspect` (`no_shares`); an ISIN that fails shape or check digit becomes None
    and the row `suspect` (`bad_isin`); a missing name makes it `rejected`. Differing
    trading and reporting currencies are normal (BP.L) and not flagged. A missing trading
    currency raises ValueError: there is no honest placeholder. `known_at` is NaT, so the
    store stamps first sight.
    """
    info = payload.info
    currency = info.get("currency")
    if currency is None:
        raise ValueError(f"{payload.symbol}: Yahoo info has no trading currency")
    trading, divisor = to_major(str(currency))
    reporting: str | None = None
    reasons: list[str] = []
    if (financial := _text(info, "financialCurrency")) is not None:
        try:
            reporting = to_major(financial)[0]
        except ValueError:
            reasons.append("bad_reporting_currency")
    isin = payload.isin
    if isin is not None and not is_valid_isin(isin):
        isin = None
        reasons.append("bad_isin")
    shares = info.get("sharesOutstanding")
    if not isinstance(shares, int | float) or shares <= 0:
        shares = None
        reasons.append("no_shares")
    name = _text(info, "longName") or _text(info, "shortName")
    rejected = name is None
    quality = "rejected" if rejected else ("suspect" if reasons else "ok")
    return pd.DataFrame(
        {
            "name": [name or ""],
            "isin": [isin],
            "exchange": [mic],
            "country": [_text(info, "country")],
            "trading_currency": [trading],
            "reporting_currency": [reporting],
            "sector": [_text(info, "sector")],
            "industry": [_text(info, "industry")],
            "shares_outstanding": pd.array([shares], dtype="float64"),
            "listing_date": pd.to_datetime([_listing_date(info)]).astype("datetime64[ns]"),
            "business_summary": [_text(info, "longBusinessSummary")],
            "repairs": [["minor_unit"] if divisor != 1 else []],
            "quality": [quality],
            "quality_reasons": [(["no_name"] if rejected else []) + reasons],
            "known_at": pd.to_datetime([None], utc=True).astype("datetime64[ns, UTC]"),
        }
    )
