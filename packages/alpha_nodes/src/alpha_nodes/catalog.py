"""The finance `SourceCatalog`: datasets plus the yfinance and edgar provider factories.

Run configs reference it as `alpha_nodes.catalog:CATALOG`. See documentation/design/finance.md,
Providers, and core.md, Source store.
"""

from lensgraph.sources import Provider, ProviderContext, SourceCatalog

from alpha_nodes.datasets import DATASETS
from alpha_nodes.providers.edgar.provider import EdgarProvider
from alpha_nodes.providers.yfinance.provider import YFinanceProvider
from alpha_nodes.settings import FinanceSettings


def _yfinance(ctx: ProviderContext) -> Provider:
    """Factory for the yfinance provider, caching under the store's provider cache directory."""
    ctx.cache_dir.mkdir(parents=True, exist_ok=True)
    return YFinanceProvider(ctx.cache_dir, ctx.clock)


def _edgar(ctx: ProviderContext) -> Provider:
    """Factory for the EDGAR provider; ValueError naming `ALPHA_NODES_SEC_USER_AGENT` when it is unset."""
    user_agent = FinanceSettings().sec_user_agent
    if not user_agent or not user_agent.strip():
        raise ValueError("the edgar provider needs ALPHA_NODES_SEC_USER_AGENT (SEC requires a User-Agent)")
    ctx.cache_dir.mkdir(parents=True, exist_ok=True)
    return EdgarProvider(ctx.cache_dir, ctx.clock, user_agent=user_agent)


CATALOG = SourceCatalog(datasets=DATASETS, providers={"yfinance": _yfinance, "edgar": _edgar})
