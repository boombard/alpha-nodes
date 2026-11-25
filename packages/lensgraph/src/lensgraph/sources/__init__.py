"""Source store contracts: models, provider/store/clock protocols, clocks."""

from .base import Clock, Provider, SourceStore, SourceUnavailable
from .clock import FakeClock, SystemClock
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

__all__ = [
    "FACT_META_COLUMNS",
    "AttemptKind",
    "Clock",
    "Dataset",
    "DateInterval",
    "FakeClock",
    "FetchAttempt",
    "FetchOutcome",
    "IntervalSet",
    "NormalisedMeta",
    "OutcomeKind",
    "Provider",
    "ProviderCapabilities",
    "Quality",
    "RateLimitPolicy",
    "RawResponse",
    "SourceSlice",
    "SourceStore",
    "SourceUnavailable",
    "SystemClock",
    "WorkItem",
]
