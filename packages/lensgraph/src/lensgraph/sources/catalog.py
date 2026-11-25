"""Wiring the source store from a run config: the domain's `SourceCatalog` and the `sources:` section.

A domain publishes a `SourceCatalog` (its datasets and provider factories); a run YAML's
`sources:` section picks providers per dataset and `build_source_store` assembles the store.
See documentation/design/core.md, Run configuration and Source store.
"""

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SkipValidation

from ..graph import ParamsError
from ..store.base import BlobStore
from .base import Clock, Provider
from .clock import SystemClock
from .duckdb_store import DuckDBSourceStore
from .models import Dataset, RateLimitPolicy


class ProviderContext(BaseModel):
    """What a provider factory gets when the store is built.

    Args:
        cache_dir: `<store_root>/provider_cache/<provider name>`, for the provider's own caches.
        clock: the store's clock.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    cache_dir: Path
    clock: SkipValidation[Clock]  # a protocol, not checked at runtime


class SourceCatalog(BaseModel):
    """A domain's datasets and provider factories, by name; referenced by `SourcesConfig.catalog`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    datasets: dict[str, Dataset]
    providers: dict[str, Callable[[ProviderContext], Provider]]


class SourcesConfig(BaseModel):
    """The `sources:` section of a run YAML.

    Args:
        catalog: "module:attr" of a `SourceCatalog` (or a zero-arg factory returning one).
        providers: dataset name -> provider names, primary first. Only listed datasets are served.
        offline: never call a provider; gaps raise `SourceUnavailable` (CLI `--offline` overrides).
        limits: provider name -> `RateLimitPolicy` replacing the one the provider declares.
    """

    model_config = ConfigDict(extra="forbid")
    catalog: str
    providers: dict[str, list[str]]
    offline: bool = False
    limits: dict[str, RateLimitPolicy] = {}


def build_source_store(
    cfg: SourcesConfig,
    store_root: Path,
    blobs: BlobStore,
    *,
    clock: Clock | None = None,
    offline: bool | None = None,
) -> DuckDBSourceStore:
    """Build the DuckDB source store at `<store_root>/sources.duckdb` from `cfg`.

    `offline`, when not None, overrides `cfg.offline`. Raises `ParamsError` naming any dataset
    or provider that the catalog doesn't have, or a dataset configured with no providers.
    """
    from ..config import load_object  # config imports run; avoid a cycle at import time

    try:
        catalog = load_object(cfg.catalog)
    except (ImportError, AttributeError) as exc:
        raise ParamsError(str(exc)) from exc
    if not isinstance(catalog, SourceCatalog):
        raise ParamsError(f"sources.catalog {cfg.catalog!r} is not a SourceCatalog")
    bad_datasets = sorted(set(cfg.providers) - set(catalog.datasets))
    if bad_datasets:
        raise ParamsError(f"sources.providers names unknown datasets: {bad_datasets}")
    used = [p for chain in cfg.providers.values() for p in chain]
    bad_providers = sorted(set(used) - set(catalog.providers))
    if bad_providers:
        raise ParamsError(f"sources.providers names unknown providers: {bad_providers}")
    empty = sorted(d for d, chain in cfg.providers.items() if not chain)
    if empty:
        raise ParamsError(f"sources.providers lists no provider for datasets: {empty}")
    bad_limits = sorted(set(cfg.limits) - set(used))
    if bad_limits:
        raise ParamsError(f"sources.limits names unused providers: {bad_limits}")
    clock = clock or SystemClock()
    built: dict[str, Provider] = {}
    for name in dict.fromkeys(used):
        ctx = ProviderContext(cache_dir=Path(store_root) / "provider_cache" / name, clock=clock)
        built[name] = catalog.providers[name](ctx)
    return DuckDBSourceStore(
        Path(store_root) / "sources.duckdb",
        blobs,
        {d: catalog.datasets[d] for d in cfg.providers},
        {d: [built[p] for p in chain] for d, chain in cfg.providers.items()},
        clock=clock,
        offline=cfg.offline if offline is None else offline,
        policy_overrides=cfg.limits,
    )
