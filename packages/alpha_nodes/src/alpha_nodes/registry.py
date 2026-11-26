"""The finance `NodeRegistry`, referenced by run configs as `alpha_nodes.registry:build_registry`."""

from lensgraph.registry import NodeRegistry

from alpha_nodes.lenses.price_behaviour import PriceBehaviour
from alpha_nodes.lenses.price_vs_fundamentals import PriceVsFundamentals
from alpha_nodes.lenses.quality_value import QualityValue
from alpha_nodes.nodes.fetch import Fundamentals, FxRates, News, Prices, Profile
from alpha_nodes.nodes.fundamental_calcs import (
    AnnualFundamentals,
    BalanceSheet,
    CapitalReturns,
    CashGeneration,
    FundamentalTrend,
    Profitability,
)
from alpha_nodes.nodes.news import RecentNews
from alpha_nodes.nodes.price_calcs import (
    Drawdown,
    Momentum,
    PriceChart,
    TotalReturn,
    Trend,
    Volatility,
)
from alpha_nodes.nodes.valuation_calcs import Valuation, ValuationChange


def build_registry() -> NodeRegistry:
    """A registry of the finance nodes: fetch (`prices`, `profile`, `fx`, `fundamentals`, `news`), the price,
    fundamentals and valuation calcs, `recent_news`, and the three v1 lenses.

    See documentation/design/finance.md (v1 lenses; Fundamentals).
    """
    registry = NodeRegistry()
    for node in (
        Prices, Profile, FxRates,
        TotalReturn, Momentum, Trend, Volatility, Drawdown, PriceChart,
        PriceBehaviour,
        Fundamentals, News, AnnualFundamentals, Profitability, BalanceSheet, CashGeneration,
        FundamentalTrend, Valuation, ValuationChange, CapitalReturns, RecentNews,
        QualityValue, PriceVsFundamentals,
    ):  # fmt: skip
        registry.register(node)
    return registry
