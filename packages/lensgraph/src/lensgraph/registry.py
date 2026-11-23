"""Node registry: maps node names to node classes.

Plan building resolves `inputs` names through a registry; see documentation/design/core.md, Graph.
"""

from .graph import UnknownNodeError
from .node import Node


class NodeRegistry:
    """Name -> node class lookup. A domain registers its nodes once; runs resolve by name."""

    def __init__(self) -> None:
        self._classes: dict[str, type[Node]] = {}

    def register(self, cls: type[Node]) -> type[Node]:
        """Register `cls` under `cls.name` (usable as a class decorator).

        Raises ValueError if the name is already taken.
        """
        if cls.name in self._classes:
            raise ValueError(f"node {cls.name!r} is already registered")
        self._classes[cls.name] = cls
        return cls

    def get(self, name: str) -> type[Node]:
        """Return the class registered as `name`; raises UnknownNodeError if absent."""
        try:
            return self._classes[name]
        except KeyError:
            raise UnknownNodeError(f"unknown node {name!r}") from None

    def names(self) -> list[str]:
        """Registered node names in registration order."""
        return list(self._classes)
