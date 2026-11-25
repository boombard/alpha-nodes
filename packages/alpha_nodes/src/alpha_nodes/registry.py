"""The finance `NodeRegistry`, referenced by run configs as `alpha_nodes.registry:build_registry`."""

from lensgraph.registry import NodeRegistry

from alpha_nodes.lenses.price_behaviour import PriceBehaviour
from alpha_nodes.nodes.fetch import FxRates, Prices, Profile
from alpha_nodes.nodes.price_calcs import (
    Drawdown,
    Momentum,
    PriceChart,
    TotalReturn,
    Trend,
    Volatility,
)


def build_registry() -> NodeRegistry:
    """A registry of the finance nodes: fetch (`prices`, `profile`, `fx`), the price calcs and `price_behaviour`.

    See documentation/design/finance.md (v1 lenses, price_behaviour).
    """
    registry = NodeRegistry()
    for node in (
        Prices, Profile, FxRates,
        TotalReturn, Momentum, Trend, Volatility, Drawdown, PriceChart,
        PriceBehaviour,
    ):  # fmt: skip
        registry.register(node)
    return registry
