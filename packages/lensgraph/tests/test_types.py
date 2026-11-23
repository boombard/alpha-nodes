import pytest
from lensgraph.plan import NodeKey
from lensgraph.types import Failed
from pydantic import ValidationError


def test_node_key_str_and_hashable():
    key = NodeKey(name="a", candidate="S1")
    assert str(key) == "a[S1]"
    assert str(NodeKey(name="a", candidate=None)) == "a"
    assert {key: 1}[NodeKey(name="a", candidate="S1")] == 1  # pyright: ignore[reportUnhashable]


def test_failed_is_frozen():
    failure = Failed(origin="n", candidate=None, error="boom")
    with pytest.raises(ValidationError):
        failure.error = "x"  # type: ignore[misc]
