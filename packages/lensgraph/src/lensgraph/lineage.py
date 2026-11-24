"""Citation lineage: resolve the ids a verdict cites back to the stored values behind them.

See documentation/design/core.md, Artifact store and run index ("any citable id resolves to a
stored output"). Resolution needs only the verdict's provenance input hashes and the blob
store, so it works the same for fresh runs and cache hits.
"""

import re
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from .store.base import BlobStore
from .verdict import LensVerdict

_CITE = re.compile(r"^(?P<name>[^.\[\]]+)(?:\.(?P<field>.+)|\[(?P<item>.+)\])?$")


class CitedValue(BaseModel):
    """A citation and the stored value it points at.

    Args:
        cite: the citable id as written in the claim or flag.
        source_hash: content hash of the input blob the value came from.
        value: the resolved value (frame, model, scalar, list item, ...).
        kind: "frame" / "model" / "value" for a whole input (by its type), "field" for
            `n.field`, "item" for `n[id]`.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    cite: str
    source_hash: str
    value: Any
    kind: Literal["frame", "model", "field", "item", "value"]


class UnresolvedCitation(LookupError):
    """A cite could not be resolved to a stored value; the message names the cite."""


def resolve_citation(verdict: LensVerdict, cite: str, blobs: BlobStore) -> CitedValue:
    """Resolve one cite (`n`, `n.field` or `n[id]`) via the verdict's input hashes.

    Raises `UnresolvedCitation` naming `cite` if the input hash, blob, field or item is missing.
    """
    match = _CITE.match(cite)
    if match is None:
        raise UnresolvedCitation(f"{cite}: not a citable id")
    name = match["name"]
    h = verdict.provenance.input_hashes.get(name)
    if h is None:
        raise UnresolvedCitation(f"{cite}: verdict has no input {name!r}")
    try:
        root = blobs.get(h)
    except Exception as exc:  # any store error means the blob is unavailable
        raise UnresolvedCitation(f"{cite}: blob {h} not available ({exc})") from exc
    if match["field"] is not None:
        field = match["field"]
        if not isinstance(root, BaseModel) or field not in type(root).model_fields:
            raise UnresolvedCitation(f"{cite}: input {name!r} has no field {field!r}")
        return CitedValue(cite=cite, source_hash=h, value=getattr(root, field), kind="field")
    if match["item"] is not None:
        item_id = match["item"]
        for item in root if isinstance(root, list) else []:
            if getattr(item, "id", None) == item_id:
                return CitedValue(cite=cite, source_hash=h, value=item, kind="item")
        raise UnresolvedCitation(f"{cite}: input {name!r} has no item with id {item_id!r}")
    kind = "frame" if isinstance(root, pd.DataFrame) else "model" if isinstance(root, BaseModel) else "value"
    return CitedValue(cite=cite, source_hash=h, value=root, kind=kind)


def resolve_all(verdict: LensVerdict, blobs: BlobStore) -> dict[str, CitedValue]:
    """Resolve every cite in the verdict's claims and flags; raises on the first failure."""
    cites = [c for claim in verdict.claims for c in claim.cites]
    cites += [c for flag in verdict.flags for c in flag.cites]
    return {c: resolve_citation(verdict, c, blobs) for c in dict.fromkeys(cites)}
