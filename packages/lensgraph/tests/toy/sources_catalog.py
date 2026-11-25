"""Toy datasets and two fake providers for source-store tests (no network).

`FakeAssayProvider` and `FakeBulkAssayProvider` differ in batching and rate-limit policy
so scheduler tests can tell them apart. Data is deterministic from the entity name.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pandera.pandas as pa
from lensgraph.sources import (
    Dataset,
    FetchOutcome,
    OutcomeKind,
    ProviderCapabilities,
    RateLimitPolicy,
    RawResponse,
    WorkItem,
)
from pandera.typing import Series


class AssaySchema(pa.DataFrameModel):
    """Canonical daily optical-density readings."""

    day: Series[pd.Timestamp]
    od600: Series[float] = pa.Field(gt=0)


class StrainInfoSchema(pa.DataFrameModel):
    """Canonical snapshot facts about a strain."""

    label: Series[str]
    lab: Series[str]


ASSAYS = Dataset(
    name="assays",
    frame_schema=AssaySchema,
    key_columns=("day",),
    axis="date",
    axis_column="day",
    ttl=timedelta(days=1),
    empty_ttl=timedelta(days=7),
)
STRAIN_INFO = Dataset(
    name="strain_info",
    frame_schema=StrainInfoSchema,
    key_columns=(),
    axis="none",
    ttl=timedelta(days=90),
    empty_ttl=timedelta(days=7),
)

_SPIKE_RATIO = 50.0


class _FakeProvider:
    """Shared behaviour of the toy providers; subclasses set `capabilities`.

    Attributes:
        calls: one entry per `fetch` call (the items it was given).
        script: entity -> outcome kinds to return on successive calls before falling back to "ok".
        unknown: entities answered "empty".
        settled_through: last settled day reported for date-axis items (None = interval end).
        normaliser_version_value: returned by `normaliser_version`.
        spike_days: days on which od600 is multiplied by 100.
    """

    library_version = "toy-1"
    capabilities: ProviderCapabilities

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[list[WorkItem]] = []
        self.script: dict[str, list[OutcomeKind]] = {}
        self.unknown: set[str] = set()
        self.settled_through: date | None = None
        self.normaliser_version_value = "1"
        self.spike_days: set[date] = set()

    def normaliser_version(self, dataset: str) -> str:
        """Return the configured normaliser version."""
        return self.normaliser_version_value

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        """Answer each item: scripted kind, else empty for unknown entities, else data."""
        self.calls.append(list(items))
        return [self._outcome(item) for item in items]

    def _outcome(self, item: WorkItem) -> FetchOutcome:
        queue = self.script.get(item.entity)
        if queue:
            kind = queue.pop(0)
            if kind != "ok":
                return FetchOutcome(item=item, kind=kind, message=f"scripted {kind}")
        if item.entity in self.unknown:
            return FetchOutcome(item=item, kind="empty")
        if item.dataset == STRAIN_INFO.name:
            payload = pd.DataFrame({"label": [f"strain {item.entity}"], "lab": ["lab-a"]})
            return FetchOutcome(item=item, kind="ok", payload=payload)
        assert item.interval is not None
        settled = min(item.interval.end, self.settled_through or item.interval.end)
        days = pd.date_range(item.interval.start, item.interval.end, freq="D")
        rng = np.random.default_rng(sum(map(ord, item.entity)))
        values = 1.0 + rng.uniform(0.0, 0.1, len(days))
        values = np.where([d.date() in self.spike_days for d in days], values * 100, values)
        payload = pd.DataFrame({"t": days.strftime("%Y-%m-%d"), "value": values})
        return FetchOutcome(item=item, kind="ok", payload=payload, settled_through=settled)

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        """Map raw columns to canonical ones and add quality metadata."""
        if dataset.name == STRAIN_INFO.name:
            frame = pd.DataFrame(payload).copy()
        else:
            frame = pd.DataFrame(
                {"day": pd.to_datetime(payload["t"]), "od600": payload["value"].astype(float)}
            )
        od = frame.get("od600", None)
        ratio = None if od is None else od / od.shift(1)
        quality, reasons = [], []
        for i in range(len(frame)):
            if od is not None and od.iloc[i] <= 0:
                quality.append("rejected")
                reasons.append(["non_positive"])
            elif ratio is not None and ratio.iloc[i] >= _SPIKE_RATIO:
                quality.append("suspect")
                reasons.append(["jump_x100"])
            else:
                quality.append("ok")
                reasons.append([])
        frame["repairs"] = [[] for _ in range(len(frame))]
        frame["quality"] = quality
        frame["quality_reasons"] = reasons
        return frame


class FakeAssayProvider(_FakeProvider):
    """Unbatched provider (max_batch=1) with a looser rate limit."""

    capabilities = ProviderCapabilities(
        datasets=frozenset({ASSAYS.name, STRAIN_INFO.name}),
        max_batch=1,
        rate_limit=RateLimitPolicy(concurrency=2, per_second=10, burst=2),
        pit_reliable={ASSAYS.name: True},
    )

    def __init__(self, name: str = "fake") -> None:
        super().__init__(name)


class FakeBulkAssayProvider(_FakeProvider):
    """Batching provider (max_batch=5) with a tight rate limit."""

    capabilities = ProviderCapabilities(
        datasets=frozenset({ASSAYS.name, STRAIN_INFO.name}),
        max_batch=5,
        rate_limit=RateLimitPolicy(concurrency=1, per_second=1, burst=1),
    )

    def __init__(self, name: str = "fake_bulk") -> None:
        super().__init__(name)


def make_raw(provider: str = "fake", dataset: str = "assays", entity: str = "S1") -> RawResponse:
    """A real `RawResponse` for calling `normalise` directly in tests."""
    return RawResponse(
        raw_id="raw-1",
        provider=provider,
        dataset=dataset,
        entity=entity,
        interval=None,
        payload_hash="h",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        library_version="toy-1",
    )
