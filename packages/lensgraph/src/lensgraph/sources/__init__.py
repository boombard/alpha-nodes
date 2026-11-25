"""Source store contracts: models, provider/store/clock protocols, clocks."""

from .base import Clock, Provider, SourceStore, SourceUnavailable
from .catalog import ProviderContext, SourceCatalog, SourcesConfig, build_source_store
from .clock import FakeClock, SystemClock
from .duckdb_store import DuckDBSourceStore
from .models import (
    FACT_META_COLUMNS,
    AttemptKind,
    Dataset,
    DateInterval,
    FetchAttempt,
    FetchOutcome,
    IntervalSet,
    NormalisedMeta,
    OutcomeKind,
    ProviderCapabilities,
    Quality,
    RateLimitPolicy,
    RawResponse,
    SourceSlice,
    WorkItem,
)
from .node import DatasetFetch, DatasetFetchMany

__all__ = [
    "FACT_META_COLUMNS",
    "AttemptKind",
    "Clock",
    "Dataset",
    "DatasetFetch",
    "DatasetFetchMany",
    "DateInterval",
    "DuckDBSourceStore",
    "FakeClock",
    "FetchAttempt",
    "FetchOutcome",
    "IntervalSet",
    "NormalisedMeta",
    "OutcomeKind",
    "Provider",
    "ProviderCapabilities",
    "ProviderContext",
    "Quality",
    "RateLimitPolicy",
    "RawResponse",
    "SourceCatalog",
    "SourceSlice",
    "SourceStore",
    "SourceUnavailable",
    "SourcesConfig",
    "SystemClock",
    "WorkItem",
    "build_source_store",
]
