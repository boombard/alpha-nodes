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

PRICES_NORMALISER_VERSION = "2"
"""Bump when `normalise_prices` changes behaviour; the store then renormalises."""
FX_NORMALISER_VERSION = "2"
"""Bump when `normalise_fx` changes behaviour; the store then renormalises."""

JUMP_RATIO = 50.0
"""Close / previous close at or above this (or at or below its inverse) is a suspect x100 jump."""
MAX_DIVIDEND_YIELD = 0.25
MISSING_SESSIONS_LIMIT = 1
"""Sessions missing between two consecutive bars at or above which the later bar is suspect.

Every recorded fixture, including the illiquid BMT.L, has none missing: Yahoo keeps a bar
for every session with the close carried forward (finance.md, Data quality).
"""
SPLIT_JUMP_FACTORS = (2, 3, 4, 5, 8, 10, 20)
"""Split ratios whose size (or inverse) a close-to-close move must not match."""
SPLIT_JUMP_TOLERANCE = 0.03
"""Relative distance from a split factor (or its inverse) that counts as split-sized."""
MIN_DIVIDEND_YIELD = 0.0002
"""Dividend / close below this is suspect: a pounds-vs-pence mix-up divided by 100."""
STALE_RUN = 5
"""Sessions with an identical close (and missing volume, for prices) that make a stale run."""
FX_JUMP_RATIO = 1.10
"""Close / previous close above this (or below its inverse) is a suspect fx jump."""


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


def _dedupe(payload: YFHistoryPayload) -> tuple[YFHistoryPayload, set[date]]:
    """Collapse bars sharing a local date into one; returns the payload and the dates collapsed.

    The kept row is the last with a non-NaN close (else the last); non-zero dividends and
    split values from any row of that date are carried onto it. Values are otherwise as
    stored. Returns `payload` itself when there are no duplicates.
    """
    days = _local_dates(payload)
    if len(set(days)) == len(days):
        return payload, set()
    positions: dict[date, list[int]] = {}
    for i, day in enumerate(days):
        positions.setdefault(day, []).append(i)
    col = {name: payload.columns.index(name) for name in payload.columns}
    index: list[str] = []
    data: list[list[float | None]] = []
    duplicated: set[date] = set()
    for day, rows in positions.items():
        priced = [i for i in rows if "Close" in col and payload.data[i][col["Close"]] is not None]
        keep = (priced or rows)[-1]
        row = list(payload.data[keep])
        for name in ("Dividends", "Stock Splits"):
            if name in col and not row[col[name]]:
                carried = [payload.data[i][col[name]] for i in rows if payload.data[i][col[name]]]
                if carried:
                    row[col[name]] = carried[-1]
        index.append(payload.index[keep])
        data.append(row)
        if len(rows) > 1:
            duplicated.add(day)
    return payload.model_copy(update={"index": index, "data": data}), duplicated


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


def _stale_runs(close: pd.Series, flat_ok: pd.Series, rejected: list[bool]) -> set[int]:
    """Positions in runs of at least `STALE_RUN` bars with an identical close and `flat_ok`."""
    stale: set[int] = set()
    run: list[int] = []
    for i, c in enumerate(close):
        extends = run and not rejected[i] and bool(flat_ok.iloc[i]) and c == close.iloc[run[-1]]
        if not extends:
            if len(run) >= STALE_RUN:
                stale.update(run)
            run = [i] if not rejected[i] and bool(flat_ok.iloc[i]) else []
        else:
            run.append(i)
    if len(run) >= STALE_RUN:
        stale.update(run)
    return stale


def _is_split_sized(ratio: float) -> bool:
    """True if a close-to-close ratio is within `SPLIT_JUMP_TOLERANCE` of a split factor or inverse."""
    return any(
        abs(ratio / k - 1) <= SPLIT_JUMP_TOLERANCE or abs(ratio * k - 1) <= SPLIT_JUMP_TOLERANCE
        for k in SPLIT_JUMP_FACTORS
    )


def _price_checks(
    payload: YFHistoryPayload,
    mic: str,
    close: pd.Series,
    dividends: pd.Series,
    splits: pd.Series,
    volume: pd.Series,
    duplicates: set[date],
) -> tuple[list[list[str]], list[bool]]:
    """Quality reasons and rejected flags per bar, over the whole (padded) payload.

    Context rows count: the first requested day is compared with the session before it.
    Stale runs are identical closes with *missing* volume only: zero volume is genuine
    no-trade on illiquid names (finance.md, Data quality), not a stale feed.
    """
    days = _local_dates(payload)
    reasons: list[list[str]] = [[] for _ in days]
    rejected = [bool(pd.isna(c) or c <= 0) for c in close]
    prev_close: float | None = None
    prev_day: date | None = None
    for i, day in enumerate(days):
        c = close.iloc[i]
        if day in duplicates:
            reasons[i].append("duplicate_bar")
        if not markets.is_session(mic, day):
            reasons[i].append("non_session_bar")
        if prev_close is not None and not rejected[i]:
            ratio = c / prev_close
            if ratio >= JUMP_RATIO or ratio <= 1 / JUMP_RATIO:
                reasons[i].append("jump_x100")
            elif _is_split_sized(ratio):
                reasons[i].append("unadjusted_split" if splits.iloc[i] > 0 else "split_like_jump")
        if not rejected[i]:
            dividend_yield = dividends.iloc[i] / c
            if dividend_yield > MAX_DIVIDEND_YIELD:
                reasons[i].append("dividend_yield_gt_25pct")
            elif 0 < dividend_yield < MIN_DIVIDEND_YIELD:
                reasons[i].append("dividend_yield_lt_0.02pct")
        if prev_day is not None and day > prev_day:
            gap = len(markets.sessions(mic, prev_day + timedelta(days=1), day - timedelta(days=1)))
            if gap >= MISSING_SESSIONS_LIMIT:
                reasons[i].append(f"missing_sessions:{gap}")
        if not rejected[i]:
            prev_close = float(c)
        prev_day = day
    for i in _stale_runs(close, volume.isna(), rejected):
        reasons[i].append("stale")
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
    payload, duplicates = _dedupe(payload)
    days = _local_dates(payload)
    close = _column(payload, "Close")
    dividends = _column(payload, "Dividends", 0.0).fillna(0.0)
    splits = _column(payload, "Stock Splits", 0.0).fillna(0.0)
    reasons, rejected = _price_checks(
        payload, mic, close, dividends, splits, _column(payload, "Volume"), duplicates
    )
    yf_repaired = _column(payload, "Repaired?", 0.0).fillna(0.0) > 0
    repairs = [
        (["minor_unit"] if divisor != 1 else []) + (["yf_price_repair"] if flag else [])
        for flag in yf_repaired
    ]
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
    positive is rejected. Checks mark (never change) a jump of more than 10% against the
    previous close (`fx_jump`), runs of 5 or more identical closes (`stale`) and collapsed
    duplicate bars. Only rows within the requested interval are returned.
    """
    payload, duplicates = _dedupe(payload)
    days = _local_dates(payload)
    close = _column(payload, "Close")
    rejected = [bool(pd.isna(c) or c <= 0) for c in close]
    reasons: list[list[str]] = [[] for _ in days]
    prev_close: float | None = None
    for i, c in enumerate(close):
        if days[i] in duplicates:
            reasons[i].append("duplicate_bar")
        if rejected[i]:
            reasons[i].append("non_positive_close")
            continue
        if prev_close is not None:
            ratio = c / prev_close
            if ratio > FX_JUMP_RATIO or ratio < 1 / FX_JUMP_RATIO:
                reasons[i].append("fx_jump")
        prev_close = float(c)
    for i in _stale_runs(close, pd.Series([True] * len(days)), rejected):
        reasons[i].append("stale")
    end_of_day = [datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1) for d in days]
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(days).astype("datetime64[ns]"),
            "usd_per_unit": close,
            **_meta_columns([[] for _ in days], reasons, rejected, end_of_day),
        }
    )
    return _requested_only(frame, payload)
