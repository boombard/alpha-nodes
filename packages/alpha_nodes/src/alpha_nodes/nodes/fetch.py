"""Finance fetch nodes: `prices`, `profile`, `fx`, `fundamentals` and `news`, thin subclasses of the generic dataset fetch nodes.

They read through the source store (the `sources` service), which decides whether the network is
needed. See documentation/design/finance.md (Providers, Currency) and core.md (Source store).
"""

from typing import ClassVar

from lensgraph.sources import DatasetFetch, DatasetFetchMany
from pydantic import Field


class Prices(DatasetFetch):
    """Daily OHLCV bars for the candidate's Yahoo symbol, normalised to major currency units.

    Attributes:
        lookback_days: history window; the default reaches back at least ten years.
    """

    name: ClassVar[str] = "prices"
    dataset: ClassVar[str] = "prices"
    lookback_days: int | None = 3653


class Profile(DatasetFetch):
    """The candidate's current profile row (name, exchange, currencies, sector, ...); not date-windowed."""

    name: ClassVar[str] = "profile"
    dataset: ClassVar[str] = "profile"


class Fundamentals(DatasetFetch):
    """The candidate's annual statements, every filing known as of the run; a snapshot, so no lookback."""

    name: ClassVar[str] = "fundamentals"
    dataset: ClassVar[str] = "fundamentals"


class News(DatasetFetch):
    """News items about the candidate; items accumulate across fetches. Untrusted text."""

    name: ClassVar[str] = "news"
    dataset: ClassVar[str] = "news"


class FxRates(DatasetFetchMany):
    """USD-per-unit rates for the currencies a run may need to convert, one shared node per run.

    Attributes:
        entities: currency codes to fetch.
        lookback_days: history window; the default reaches back at least ten years.
    """

    name: ClassVar[str] = "fx"
    dataset: ClassVar[str] = "fx"
    entities: list[str] = Field(
        default_factory=lambda: ["GBP", "EUR", "CHF", "SEK", "NOK", "DKK", "PLN"], min_length=1
    )
    lookback_days: int | None = 3653
