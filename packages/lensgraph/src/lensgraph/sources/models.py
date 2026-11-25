"""Data models of the source store (layer 1 cache).

Pure contracts: intervals, dataset declarations, provider capabilities, fetch
outcomes, stored raw responses and the slice a fetch node reads. No behaviour
beyond validation and interval arithmetic. See documentation/design/core.md,
Source store (layer 1 cache).
"""

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional, get_args

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_FROZEN = ConfigDict(frozen=True, extra="forbid")
_FROZEN_ARBITRARY = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

_ONE_DAY = timedelta(days=1)


class DateInterval(BaseModel):
    """Closed date interval: both `start` and `end` are included, and `start <= end`."""

    model_config = _FROZEN

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> "DateInterval":
        if self.start > self.end:
            raise ValueError(f"interval start {self.start} is after end {self.end}")
        return self


def _merge(intervals: Iterable[DateInterval]) -> tuple[DateInterval, ...]:
    """Sort and merge overlapping or day-adjacent intervals."""
    merged: list[DateInterval] = []
    for iv in sorted(intervals, key=lambda i: (i.start, i.end)):
        if merged and iv.start <= merged[-1].end + _ONE_DAY:
            if iv.end > merged[-1].end:
                merged[-1] = DateInterval(start=merged[-1].start, end=iv.end)
        else:
            merged.append(iv)
    return tuple(merged)


def _as_set(other: "IntervalSet | DateInterval") -> "IntervalSet":
    return other if isinstance(other, IntervalSet) else IntervalSet(intervals=(other,))


class IntervalSet(BaseModel):
    """A set of days stored as sorted, disjoint, non-adjacent closed intervals.

    Used for source-store coverage: the requested ranges already fetched (see
    documentation/design/core.md, Source store). Normalised on construction, so
    equal day sets compare equal.
    """

    model_config = _FROZEN

    intervals: tuple[DateInterval, ...] = ()

    @field_validator("intervals", mode="after")
    @classmethod
    def _normalise(cls, value: tuple[DateInterval, ...]) -> tuple[DateInterval, ...]:
        return _merge(value)

    def union(self, other: "IntervalSet | DateInterval") -> "IntervalSet":
        """Days in either set."""
        return IntervalSet(intervals=self.intervals + _as_set(other).intervals)

    def subtract(self, other: "IntervalSet | DateInterval") -> "IntervalSet":
        """Days in this set and not in `other` (may leave holes)."""
        result: list[DateInterval] = []
        cuts = _as_set(other).intervals
        for iv in self.intervals:
            start = iv.start
            for cut in cuts:
                if cut.end < start or cut.start > iv.end:
                    continue
                if cut.start > start:
                    result.append(DateInterval(start=start, end=cut.start - _ONE_DAY))
                start = max(start, cut.end + _ONE_DAY)
                if start > iv.end:
                    break
            if start <= iv.end:
                result.append(DateInterval(start=start, end=iv.end))
        return IntervalSet(intervals=tuple(result))

    def intersect(self, other: "IntervalSet | DateInterval") -> "IntervalSet":
        """Days in both sets."""
        result = [
            DateInterval(start=max(a.start, b.start), end=min(a.end, b.end))
            for a in self.intervals
            for b in _as_set(other).intervals
            if max(a.start, b.start) <= min(a.end, b.end)
        ]
        return IntervalSet(intervals=tuple(result))

    def covers(self, interval: DateInterval) -> bool:
        """True when every day of `interval` is in the set."""
        return any(i.start <= interval.start and interval.end <= i.end for i in self.intervals)

    def is_empty(self) -> bool:
        """True when the set holds no days."""
        return not self.intervals

    def last_day(self) -> date | None:
        """Latest day in the set, or None when empty."""
        return self.intervals[-1].end if self.intervals else None


class Dataset(BaseModel):
    """A named dataset a domain declares: canonical schema, key, coverage axis, freshness.

    The store keys everything by dataset name; providers map their raw payloads to
    `frame_schema`. See documentation/design/core.md, Source store.
    """

    model_config = _FROZEN_ARBITRARY

    name: str
    frame_schema: type[pa.DataFrameModel]  # canonical columns only (no fact meta columns)
    key_columns: tuple[str, ...]  # identify one fact within an entity; () for a snapshot
    axis: Literal["date", "none"]  # "none" = snapshot data (one current row set per entity)
    axis_column: str | None = None  # required when axis == "date"
    ttl: timedelta  # freshness of snapshots and of the unsettled tail
    empty_ttl: timedelta  # how long an `empty` outcome suppresses refetching

    @model_validator(mode="after")
    def _axis_column(self) -> "Dataset":
        if self.axis == "date" and not self.axis_column:
            raise ValueError("axis='date' requires axis_column")
        return self


class RateLimitPolicy(BaseModel):
    """A provider's declared limits and give-up thresholds; the core's limiter obeys it."""

    model_config = _FROZEN

    concurrency: int = 1
    per_second: float | None = None
    burst: int = 1
    backoff_s: tuple[float, ...] = (30.0, 60.0, 120.0, 240.0)  # provider-wide pause per episode
    jitter: float = 0.1  # fraction of each pause added at random
    max_rate_limit_episodes: int = 3  # consecutive episodes before GlobalFailure
    max_unreachable: int = 5  # consecutive unreachable outcomes before GlobalFailure
    max_error_retries: int = 2  # retries of a transient `error` item before giving up on it
    max_consecutive_errors: int | None = None  # distinct entities ending in `error`, in a row, before GlobalFailure
    max_consecutive_empty: int | None = None  # distinct entities answering `empty`, in a row, before GlobalFailure


class ProviderCapabilities(BaseModel):
    """What the core may know about a provider: datasets, batching, limits, PIT reliability."""

    model_config = _FROZEN

    datasets: frozenset[str]
    max_batch: int = 1  # entities per provider call; 1 = no batching
    rate_limit: RateLimitPolicy
    pit_reliable: dict[str, bool] = {}  # per dataset; missing = False


class WorkItem(BaseModel):
    """One (dataset, entity, interval, params) unit the scheduler hands to a provider."""

    model_config = _FROZEN

    dataset: str
    entity: str
    interval: DateInterval | None  # None for axis="none"
    params: dict[str, str] = {}


OutcomeKind = Literal["ok", "empty", "error", "rate_limited", "unreachable"]


class FetchOutcome(BaseModel):
    """A provider's answer for one work item (see core.md, Source store, outcome classes)."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    item: WorkItem
    kind: OutcomeKind
    payload: Any = None  # BlobStore-encodable (frame, model, JSON); required when kind == "ok"
    settled_through: date | None = None  # axis="date": last settled day; later rows aren't facts
    restated_before: date | None = None  # provider says stored facts before this day changed
    message: str = ""

    @model_validator(mode="after")
    def _ok_has_payload(self) -> "FetchOutcome":
        if self.kind == "ok" and self.payload is None:
            raise ValueError("an 'ok' outcome requires a payload")
        return self


class RawResponse(BaseModel):
    """One stored provider response, immutable. Facts are rebuilt from these on renormalise."""

    model_config = _FROZEN

    raw_id: str
    provider: str
    dataset: str
    entity: str
    interval: DateInterval | None
    params: dict[str, str] = {}
    payload_hash: str  # BlobStore hash of the verbatim payload
    fetched_at: datetime
    library_version: str


AttemptKind = OutcomeKind | Literal["unsettled"]


class FetchAttempt(BaseModel):
    """One row of the fetch-attempt log (every attempt, with outcome and timestamp)."""

    model_config = _FROZEN

    provider: str
    dataset: str
    entity: str
    interval: DateInterval | None
    params: dict[str, str] = {}
    kind: AttemptKind
    at: datetime
    message: str = ""


Quality = Literal["ok", "suspect", "rejected"]


class NormalisedMeta(pa.DataFrameModel):
    """Columns `Provider.normalise` adds next to the canonical ones."""

    repairs: Series[object]  # list[str] per row, e.g. ["minor_unit"]; [] when none
    quality: Series[str] = pa.Field(isin=list(get_args(Quality)))  # a `Quality`
    quality_reasons: Series[object]  # list[str]; non-empty when quality != "ok"
    known_at: Optional[Series[pd.DatetimeTZDtype]] = pa.Field(  # noqa: UP045 (pandera Optional)
        nullable=True, dtype_kwargs={"unit": "ns", "tz": "UTC"}
    )  # provider publication time; the store fills first_seen_at when the column is absent

    class Config:
        """Extra (canonical) columns are allowed alongside the meta columns."""

        strict = False


FACT_META_COLUMNS: tuple[str, ...] = (
    "entity",
    "provider",
    "fetch_id",
    "first_seen_at",
    "known_at",
    "normaliser_version",
    "repairs",
    "quality",
    "quality_reasons",
)
"""Columns the store adds to canonical columns to make a stored fact."""


class SourceSlice(BaseModel):
    """What a fetch node reads: facts for one entity, canonical + `FACT_META_COLUMNS`."""

    model_config = _FROZEN_ARBITRARY

    dataset: str
    entity: str
    provider: str | None  # who served it; None when empty
    frame: pd.DataFrame  # sorted by key columns
    pit_reliable: bool
    empty: bool  # True for a legitimate empty (unknown entity, no data)
