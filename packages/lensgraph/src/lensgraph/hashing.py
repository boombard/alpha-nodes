"""Stable content hashing and memo keys.

Hashes must be identical across processes (no reprs, no hash-seed-dependent ordering) so the
persistent cache can hit; see documentation/design/core.md, Memoization.
"""

import hashlib
import math
from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from pydantic import BaseModel

if TYPE_CHECKING:
    from .node import Node


def _feed(h: "hashlib._Hash", value: Any) -> None:
    """Feed a type-tagged, length-prefixed canonical encoding of `value` into hash `h`.

    Raises TypeError for types with no stable encoding rather than guessing.
    """
    def tag(t: str, payload: str = "") -> None:
        data = f"{t}:{payload}".encode()
        h.update(len(data).to_bytes(8, "big") + data)

    if value is None:
        tag("none")
    elif isinstance(value, pd.DataFrame):
        tag("df", repr(list(map(str, value.columns))) + repr([str(t) for t in value.dtypes]))
        row_hashes = pd.util.hash_pandas_object(value, index=True)  # pyright: ignore[reportAttributeAccessIssue]
        h.update(row_hashes.to_numpy().tobytes())
    elif isinstance(value, BaseModel):
        cls = type(value)
        tag("model", f"{cls.__module__}.{cls.__qualname__}")
        for field in sorted(cls.model_fields):
            _feed(h, field)
            _feed(h, getattr(value, field))
    elif isinstance(value, Mapping):
        tag("dict", str(len(value)))
        for k in sorted(value, key=repr):
            _feed(h, k)
            _feed(h, value[k])
    elif isinstance(value, list | tuple):
        tag(type(value).__name__, str(len(value)))
        for item in value:
            _feed(h, item)
    elif isinstance(value, set | frozenset):
        tag("set", str(len(value)))
        for item in sorted(value, key=repr):
            _feed(h, item)
    elif isinstance(value, bool | np.bool_):
        tag("bool", str(bool(value)))
    elif isinstance(value, float | np.floating):
        f = float(value)
        tag("float", "nan" if math.isnan(f) else repr(f))
    elif isinstance(value, int | np.integer):
        tag("int", str(int(value)))
    elif isinstance(value, str):
        tag("str", value)
    elif isinstance(value, bytes):
        tag("bytes")
        h.update(value)
    elif isinstance(value, pd.Series):
        tag("series", f"{value.dtype}|{value.name!r}")
        row_hashes = pd.util.hash_pandas_object(value, index=True)  # pyright: ignore[reportAttributeAccessIssue]
        h.update(row_hashes.to_numpy().tobytes())
    elif isinstance(value, np.ndarray):
        tag("ndarray", f"{value.dtype}|{value.shape}")
        h.update(np.ascontiguousarray(value).tobytes())
    elif isinstance(value, date | pd.Timestamp):  # datetime is a date subclass
        tag(type(value).__qualname__, value.isoformat())
    else:
        raise TypeError(f"content_hash: unsupported type {type(value).__qualname__}")


def content_hash(value: Any) -> str:
    """SHA-256 hex digest of a value's content; stable across processes.

    Used for blob addresses and node output hashes (early cutoff). `None` and `Absent` differ,
    NaN hashes stably, dict/set order is irrelevant, list/tuple/frame row order matters.
    """
    h = hashlib.sha256()
    _feed(h, value)
    return h.hexdigest()


def memo_key(
    node: "Node", input_hashes: Mapping[str, str], candidate_id: str | None, salt: str = ""
) -> str:
    """Memo cache key for one node execution; see documentation/design/core.md, Memoization.

    Covers node name, code version (the literal "fetch" for nodes that ignore their source),
    params, upstream output hashes, candidate id and `salt` (from `Node.memo_salt`).
    """
    return content_hash(
        [
            node.name,
            node.code_version() if node.hash_source else "fetch",
            {f: getattr(node, f) for f in type(node).model_fields},  # params, not class identity
            dict(sorted(input_hashes.items())),
            candidate_id,
            salt,
        ]
    )
