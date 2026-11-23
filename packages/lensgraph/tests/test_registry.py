"""Tests for NodeRegistry: registration, lookup and error cases."""

from typing import ClassVar

import pytest
from lensgraph.graph import GraphError, UnknownNodeError
from lensgraph.node import CalcNode
from lensgraph.registry import NodeRegistry
from toy.nodes import AssayRaw, GrowthRate


def test_register_and_get_roundtrip() -> None:
    registry = NodeRegistry()
    registry.register(AssayRaw)
    registry.register(GrowthRate)
    assert registry.get("assay_raw") is AssayRaw
    assert registry.names() == ["assay_raw", "growth_rate"]


def test_register_works_as_decorator() -> None:
    registry = NodeRegistry()

    @registry.register
    class Deco(CalcNode):
        name: ClassVar[str] = "deco"

    assert registry.get("deco") is Deco


def test_register_duplicate_raises() -> None:
    registry = NodeRegistry()
    registry.register(AssayRaw)
    with pytest.raises(ValueError, match="assay_raw"):
        registry.register(AssayRaw)


def test_get_unknown_raises() -> None:
    with pytest.raises(UnknownNodeError, match="nope"):
        NodeRegistry().get("nope")


def test_unknown_node_error_is_graph_error() -> None:
    assert issubclass(UnknownNodeError, GraphError)
