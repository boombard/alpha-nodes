"""Toy fetch nodes over the fake source-store datasets, plus a `SourceCatalog` for run configs.

`sources_run.yaml` points at `CATALOG` and `build_registry`. Providers created through the
catalog are remembered in `CREATED` so tests can inspect their `calls`.
"""

from typing import Any, ClassVar

import pandas as pd
from lensgraph.node import CalcNode, NodeContext, TransformNode
from lensgraph.registry import NodeRegistry
from lensgraph.sources import Provider
from lensgraph.sources.catalog import ProviderContext, SourceCatalog
from lensgraph.sources.node import DatasetFetch, DatasetFetchMany

from .sources_catalog import ASSAYS, STRAIN_INFO, FakeAssayProvider, FakeBulkAssayProvider

CREATED: dict[str, Provider] = {}  # provider name -> the instance the catalog last built


def _make(cls: type[FakeAssayProvider] | type[FakeBulkAssayProvider]):
    def factory(ctx: ProviderContext) -> Provider:
        provider = cls()
        CREATED[provider.name] = provider
        return provider

    return factory


CATALOG = SourceCatalog(
    datasets={ASSAYS.name: ASSAYS, STRAIN_INFO.name: STRAIN_INFO},
    providers={"fake": _make(FakeAssayProvider), "fake_bulk": _make(FakeBulkAssayProvider)},
)


class StrainAssays(DatasetFetch):
    """Per-strain assay readings of the last five days."""

    name: ClassVar[str] = "strain_assays"
    dataset: ClassVar[str] = "assays"
    lookback_days: int | None = 5


class StrainLabel(DatasetFetch):
    """Per-strain snapshot facts (the lab); no window."""

    name: ClassVar[str] = "strain_label"
    dataset: ClassVar[str] = "strain_info"


class AssayMean(CalcNode):
    """Mean od600 of a strain's recent readings."""

    name: ClassVar[str] = "assay_mean"
    inputs: ClassVar[dict[str, str]] = {"assays": "strain_assays"}
    output: ClassVar[Any] = float

    def run(self, ctx: NodeContext, assays: pd.DataFrame) -> float:
        return float(assays["od600"].to_numpy(dtype=float).mean())


class LabUpper(TransformNode):
    """Upper-cased lab of a strain; counts how often it really ran in `RUNS`."""

    name: ClassVar[str] = "lab_upper"
    inputs: ClassVar[dict[str, str]] = {"info": "strain_label"}
    output: ClassVar[Any] = str
    RUNS: ClassVar[list[str]] = []

    def run(self, ctx: NodeContext, info: pd.DataFrame) -> str:
        assert ctx.candidate is not None
        self.RUNS.append(ctx.candidate.id)
        return str(info["lab"].iloc[0]).upper()


class AssayPanel(DatasetFetchMany):
    """Shared read of two fixed strains' assays."""

    name: ClassVar[str] = "assay_panel"
    dataset: ClassVar[str] = "assays"
    entities: list[str] = ["S1", "S2"]  # noqa: RUF012
    lookback_days: int | None = 3


def build_registry() -> NodeRegistry:
    """Registry of the toy source-backed nodes."""
    registry = NodeRegistry()
    for cls in (StrainAssays, StrainLabel, AssayMean, LabUpper, AssayPanel):
        registry.register(cls)
    return registry
