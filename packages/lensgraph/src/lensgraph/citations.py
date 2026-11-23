"""Citable ids: the closed set of strings a claim or flag may cite.

See documentation/design/core.md, AI nodes (guard rails).
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

_CONTAINERS = (list, tuple, set, frozenset, dict, BaseModel)


def citable_ids(inputs: Mapping[str, Any]) -> frozenset[str]:
    """Ids a lens may cite about its `inputs`.

    Yields `n` for every input name, `n.<field>` for each scalar field of a model value,
    and `n[<id>]` for each item of a list of models that have an `id`. Frames give only `n`.
    """
    ids: set[str] = set()
    for name, value in inputs.items():
        ids.add(name)
        if isinstance(value, BaseModel):
            for field in type(value).model_fields:
                if not isinstance(getattr(value, field), _CONTAINERS):
                    ids.add(f"{name}.{field}")
        elif isinstance(value, list):
            for item in value:
                item_id = getattr(item, "id", None) if isinstance(item, BaseModel) else None
                if item_id is not None:
                    ids.add(f"{name}[{item_id}]")
    return frozenset(ids)
