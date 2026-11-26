"""Finance fetch nodes: `prices`, `profile`, `fx`, `fundamentals` and `news`, thin subclasses of the generic dataset fetch nodes.

They read through the source store (the `sources` service), which decides whether the network is
needed. See documentation/design/finance.md (Providers, Currency) and core.md (Source store).
"""

from typing import ClassVar

from lensgraph.sources import DatasetFetch, DatasetFetchMany
from pydantic import Field

from alpha_nodes.datasets import DATASETS


class Prices(DatasetFetch):
    """Daily OHLCV bars for the candidate's Yahoo symbol, normalised to major currency units.

    Attributes:
        lookback_days: history window; the default reaches back at least ten years.
    """

    name: ClassVar[str] = "prices"
    dataset: ClassVar[str] = "prices"
    frame_schema = DATASETS["prices"].frame_schema
    lookback_days: int | None = 3653


class Profile(DatasetFetch):
    """The candidate's current profile row (name, exchange, currencies, sector, ...); not date-windowed."""

    name: ClassVar[str] = "profile"
    dataset: ClassVar[str] = "profile"
    frame_schema = DATASETS["profile"].frame_schema


class Fundamentals(DatasetFetch):
    """The candidate's annual statements, every filing known as of the run; a snapshot, so no lookback."""

    name: ClassVar[str] = "fundamentals"
    dataset: ClassVar[str] = "fundamentals"
    frame_schema = DATASETS["fundamentals"].frame_schema


class News(DatasetFetch):
    """News items about the candidate; items accumulate across fetches. Untrusted text."""

    name: ClassVar[str] = "news"
    dataset: ClassVar[str] = "news"
    frame_schema = DATASETS["news"].frame_schema


class FxRates(DatasetFetchMany):
    """USD-per-unit rates for the currencies a run may need to convert, one shared node per run.

    Attributes:
        entities: currency codes to fetch.
        lookback_days: history window; the default reaches back at least ten years.
    """

    name: ClassVar[str] = "fx"
    dataset: ClassVar[str] = "fx"
    frame_schema = DATASETS["fx"].frame_schema
    entities: list[str] = Field(
        default_factory=lambda: ["GBP", "EUR", "CHF", "SEK", "NOK", "DKK", "PLN"], min_length=1
    )
    lookback_days: int | None = 3653
