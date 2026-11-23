"""Fake source for the toy domain; stands in for a real data provider (e.g. a market-data API)."""

import numpy as np
import pandas as pd
from lensgraph.types import GlobalFailure

from .nodes import ToxNote


class FakeAssaySource:
    """Deterministic in-memory assay source that records every call.

    Tests use `calls` to prove caching (no refetch) and `fail_for` to simulate outages.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []  # one entry per source call, e.g. "assays:S1"
        self.fail_for: set[str] = set()  # strains whose calls raise GlobalFailure

    def _record(self, call: str, strain: str | None = None) -> None:
        self.calls.append(call)
        if strain in self.fail_for:
            raise GlobalFailure(f"source down for {strain}")

    def assays(self, strain: str) -> pd.DataFrame:
        """Growth-curve readings (time_h, od600). S3 lacks od600: the bad-data case."""
        self._record(f"assays:{strain}", strain)
        rng = np.random.default_rng(sum(map(ord, strain)))
        frame = pd.DataFrame(
            {
                "time_h": np.arange(10, dtype=float),
                "od600": np.cumsum(rng.uniform(0.05, 0.2, 10)) + 0.1,
            }
        )
        if strain == "S3":
            frame = frame.drop(columns=["od600"])
        return frame

    def reference(self) -> pd.DataFrame:
        """Shared reference panel, the same for every strain."""
        self._record("reference")
        return pd.DataFrame({"strain": ["REF"], "growth_rate": [0.5]})

    def tox_notes(self, strain: str) -> list[ToxNote]:
        """Free-text toxicity notes (stand-in for filings/news). S2 has none."""
        self._record(f"tox_notes:{strain}", strain)
        if strain == "S2":
            return []
        return [ToxNote(id=f"{strain}-n1", text=f"{strain} shows mild toxicity")]
