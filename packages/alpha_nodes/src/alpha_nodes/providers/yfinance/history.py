"""yfinance chart payloads: the stored raw model, and its normalisation to prices and fx.

See documentation/design/finance.md, "Data quality: yfinance quirks" and Prices and
point-in-time.
"""

import json
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
from pydantic import BaseModel

from alpha_nodes import markets
from alpha_nodes.units import to_major

PRICES_NORMALISER_VERSION = "1"
"""Bump when `normalise_prices` changes behaviour; the store then renormalises."""
FX_NORMALISER_VERSION = "1"
"""Bump when `normalise_fx` changes behaviour; the store then renormalises."""

JUMP_RATIO = 50.0
"""Close / previous close at or above this (or at or below its inverse) is a suspect x100 jump."""
MAX_DIVIDEND_YIELD = 0.25
MISSING_SESSIONS_LIMIT = 3


class YFHistoryPayload(BaseModel):
    """The verbatim chart response for one symbol, JSON-safe; stored as the raw payload.

    Facts are rebuilt from this on renormalise (core.md, Source store).
    """

    symbol: str
    metadata: dict[str, Any]  # yfinance `history_metadata`, JSON-safe copy
    columns: list[str]  # as returned, e.g. Open High Low Close ... Repaired?
    index: list[str]  # ISO timestamps with offset
    data: list[list[float | None]]
    requested_start: date
    requested_end: date


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def payload_from_history(
    symbol: str, frame: pd.DataFrame, metadata: dict[str, Any], start: date, end: date
) -> YFHistoryPayload:
    """Capture a `Ticker.history` frame and metadata as a `YFHistoryPayload`.

    `start`/`end` are the requested interval (inclusive), not the padded request.
    """
    data = [
        [None if (isinstance(v, float) and math.isnan(v)) else float(v) for v in row]
        for row in frame.astype(float).itertuples(index=False, name=None)
    ]
    return YFHistoryPayload(
        symbol=symbol,
        metadata=_json_safe(dict(metadata)),
        columns=[str(c) for c in frame.columns],
        index=[ts.isoformat() for ts in frame.index],
        data=data,
        requested_start=start,
        requested_end=end,
    )


def _local_dates(payload: YFHistoryPayload) -> list[date]:
    """Exchange-local trading date of each bar: the date part of the offset-aware timestamp."""
    return [date.fromisoformat(ts[:10]) for ts in payload.index]


def _column(payload: YFHistoryPayload, name: str, default: float | None = None) -> pd.Series:
    if name not in payload.columns:
        return pd.Series([default] * len(payload.index), dtype="float64")
    pos = payload.columns.index(name)
    return pd.Series([row[pos] for row in payload.data], dtype="float64")


def _meta_columns(
    repairs: list[list[str]], reasons: list[list[str]], rejected: list[bool], known_at: list[Any]
) -> dict[str, Any]:
    quality = [
        "rejected" if rej else ("suspect" if why else "ok")
        for rej, why in zip(rejected, reasons, strict=True)
    ]
    return {
        "repairs": repairs,
        "quality": quality,
        "quality_reasons": reasons,
        "known_at": pd.to_datetime(known_at, utc=True).astype("datetime64[ns, UTC]"),
    }


def _price_checks(
    payload: YFHistoryPayload, mic: str, close: pd.Series, dividends: pd.Series
) -> tuple[list[list[str]], list[bool]]:
    """Quality reasons and rejected flags per bar, over the whole (padded) payload.

    Context rows count: the first requested day is compared with the session before it.
    """
    days = _local_dates(payload)
    reasons: list[list[str]] = [[] for _ in days]
    rejected = [bool(pd.isna(c) or c <= 0) for c in close]
    prev_close: float | None = None
    prev_day: date | None = None
    for i, day in enumerate(days):
        c = close.iloc[i]
        if not markets.is_session(mic, day):
            reasons[i].append("non_session_bar")
        if prev_close is not None and not rejected[i]:
            ratio = c / prev_close
            if ratio >= JUMP_RATIO or ratio <= 1 / JUMP_RATIO:
                reasons[i].append("jump_x100")
        if not rejected[i] and dividends.iloc[i] / c > MAX_DIVIDEND_YIELD:
            reasons[i].append("dividend_yield_gt_25pct")
        if prev_day is not None and day > prev_day:
            gap = len(markets.sessions(mic, prev_day + timedelta(days=1), day - timedelta(days=1)))
            if gap >= MISSING_SESSIONS_LIMIT:
                reasons[i].append(f"missing_sessions:{gap}")
        if not rejected[i]:
            prev_close = float(c)
        prev_day = day
    return reasons, rejected


def _requested_only(frame: pd.DataFrame, payload: YFHistoryPayload) -> pd.DataFrame:
    """Keep rows inside the requested interval; padding rows were context only."""
    start, end = pd.Timestamp(payload.requested_start), pd.Timestamp(payload.requested_end)
    inside = (frame["date"] >= start) & (frame["date"] <= end)
    return pd.DataFrame(frame[inside]).reset_index(drop=True)


def normalise_prices(payload: YFHistoryPayload, mic: str) -> pd.DataFrame:
    """Map a chart payload to `PriceSchema` columns plus the `NormalisedMeta` columns.

    Repairs: minor-unit currencies (GBp) are divided to major units; yfinance's own
    `Repaired?` flag is carried as `yf_price_repair`. Checks mark rows suspect or rejected
    but never change values (finance.md, Data quality). `known_at` is the session close;
    bars on non-session days get NaT. Checks run over the whole padded payload, but only rows
    within the requested interval are returned (coverage never recorded the padding).
    """
    # An empty interval carries no metadata; with no rows there is nothing to label.
    major, divisor = to_major(str(payload.metadata["currency"])) if payload.index else ("USD", 1)
    days = _local_dates(payload)
    close = _column(payload, "Close")
    dividends = _column(payload, "Dividends", 0.0).fillna(0.0)
    reasons, rejected = _price_checks(payload, mic, close, dividends)
    yf_repaired = _column(payload, "Repaired?", 0.0).fillna(0.0) > 0
    repairs = [
        (["minor_unit"] if divisor != 1 else []) + (["yf_price_repair"] if flag else [])
        for flag in yf_repaired
    ]
    splits = _column(payload, "Stock Splits", 0.0).fillna(0.0)
    known_at = [markets.session_close(mic, d) if markets.is_session(mic, d) else None for d in days]
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(days).astype("datetime64[ns]"),
            "open": _column(payload, "Open") / divisor,
            "high": _column(payload, "High") / divisor,
            "low": _column(payload, "Low") / divisor,
            "close": close / divisor,
            "volume": pd.array(_column(payload, "Volume").round(), dtype="Int64"),
            "dividends": dividends / divisor,
            "split_ratio": splits.where(splits > 0, 1.0),
            "currency": [major] * len(days),
            **_meta_columns(repairs, reasons, rejected, known_at),
        }
    )
    return _requested_only(frame, payload)


def normalise_fx(payload: YFHistoryPayload) -> pd.DataFrame:
    """Map a `<CCY>USD=X` chart payload to `FxSchema` columns plus the meta columns.

    `usd_per_unit` is the close. `known_at` is the end of that UTC day. A close that is not
    positive is rejected. Only rows within the requested interval are returned.
    """
    days = _local_dates(payload)
    close = _column(payload, "Close")
    rejected = [bool(pd.isna(c) or c <= 0) for c in close]
    end_of_day = [datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1) for d in days]
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(days).astype("datetime64[ns]"),
            "usd_per_unit": close,
            **_meta_columns(
                [[] for _ in days],
                [["non_positive_close"] if rej else [] for rej in rejected],
                rejected,
                end_of_day,
            ),
        }
    )
    return _requested_only(frame, payload)
