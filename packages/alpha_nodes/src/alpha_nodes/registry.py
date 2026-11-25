"""The finance `NodeRegistry`, referenced by run configs as `alpha_nodes.registry:build_registry`."""

from lensgraph.registry import NodeRegistry

from alpha_nodes.nodes.fetch import FxRates, Prices, Profile


def build_registry() -> NodeRegistry:
    """A registry holding the finance fetch nodes (`prices`, `profile`, `fx`)."""
    registry = NodeRegistry()
    for node in (Prices, Profile, FxRates):
        registry.register(node)
    return registry
