"""Protocols the source store is built from: `Clock`, `Provider`, `SourceStore`.

Domains implement `Provider`; the core implements `SourceStore` (DuckDB, over a
`BlobStore` from store/base.py). See documentation/design/core.md, Source store.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from .models import (
    Dataset,
    DateInterval,
    FetchAttempt,
    FetchOutcome,
    IntervalSet,
    ProviderCapabilities,
    RawResponse,
    SourceSlice,
    WorkItem,
)


class SourceUnavailable(Exception):
    """Data cannot be served: an offline gap, or an `error` outcome after retries.

    The fetch node fails with it (a per-candidate failure, unlike `GlobalFailure`).
    """


class Clock(Protocol):
    """Time source, injectable so TTL and backoff are testable."""

    def now(self) -> datetime:
        """Current time, tz-aware UTC."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Wait `seconds`."""
        ...


@runtime_checkable
class Provider(Protocol):
    """A data-source adapter. The core knows it only through `capabilities`."""

    name: str
    capabilities: ProviderCapabilities
    library_version: str

    def normaliser_version(self, dataset: str) -> str:
        """Version of the mapping to canonical schema; a change triggers renormalise."""
        ...

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        """Blocking I/O: one outcome per item, same order. May raise `GlobalFailure`."""
        ...

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        """Map a raw payload to canonical columns plus the `NormalisedMeta` columns."""
        ...


class SourceStore(Protocol):
    """Point-in-time cache of fetched data, shared across runs."""

    async def get(
        self,
        dataset: str,
        entity: str,
        interval: DateInterval | None = None,
        *,
        as_of: date | None = None,
        params: Mapping[str, str] = {},
        include_rejected: bool = False,
    ) -> SourceSlice:
        """Serve from the store, fetching gaps first. Raises `SourceUnavailable`."""
        ...

    async def ensure(
        self,
        dataset: str,
        entities: Sequence[str],
        interval: DateInterval | None = None,
        *,
        params: Mapping[str, str] = {},
    ) -> None:
        """Fill gaps for many entities at once (batched)."""
        ...

    def query(
        self,
        dataset: str,
        entity: str,
        interval: DateInterval | None = None,
        *,
        as_of: date | None = None,
        params: Mapping[str, str] = {},
        include_rejected: bool = False,
    ) -> SourceSlice:
        """Read what is stored; never fetches."""
        ...

    def renormalise(self, dataset: str, provider: str) -> int:
        """Rebuild facts from stored raw responses; returns rows written."""
        ...

    def attempts(self, dataset: str | None = None, entity: str | None = None) -> list[FetchAttempt]:
        """The fetch-attempt log, optionally filtered."""
        ...

    def coverage(
        self, dataset: str, entity: str, provider: str, params: Mapping[str, str] = {}
    ) -> IntervalSet:
        """Requested ranges successfully fetched for this (entity, dataset, provider, params)."""
        ...
