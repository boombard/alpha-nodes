"""The finance `SourceCatalog`: datasets plus the yfinance provider factory.

Run configs reference it as `alpha_nodes.catalog:CATALOG`. See documentation/design/finance.md,
Providers, and core.md, Source store.
"""

from lensgraph.sources import Provider, ProviderContext, SourceCatalog

from alpha_nodes.datasets import DATASETS
from alpha_nodes.providers.yfinance.provider import YFinanceProvider


def _yfinance(ctx: ProviderContext) -> Provider:
    """Factory for the yfinance provider, caching under the store's provider cache directory."""
    ctx.cache_dir.mkdir(parents=True, exist_ok=True)
    return YFinanceProvider(ctx.cache_dir, ctx.clock)


CATALOG = SourceCatalog(datasets=DATASETS, providers={"yfinance": _yfinance})
