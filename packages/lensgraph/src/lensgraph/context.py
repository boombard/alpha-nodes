"""Rendering node outputs as the user message of an AI lens.

Every citable id (see citations.py) gets a block headed `### [<id>]`, so the model can only be
told about, and cite, ids the guard rail will accept. See documentation/design/core.md,
AI nodes (guard rails), Context assembly.
"""

import json
from collections.abc import Mapping
from typing import Any

import pandas as pd
from pydantic import BaseModel

from .citations import citable_ids
from .types import Absent


def unavailable_inputs(inputs: Mapping[str, Any]) -> frozenset[str]:
    """Names of inputs with nothing to show (absent, None or an empty list); never citable."""
    return frozenset(
        n
        for n, v in inputs.items()
        if v is None or isinstance(v, Absent) or (isinstance(v, list | tuple) and not v)
    )


def _json(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    return json.dumps(value, default=str)


def _block(cid: str, body: str) -> str:
    return f"### [{cid}]\n{body}"


def _frame_body(frame: pd.DataFrame, max_rows: int) -> str:
    csv = frame.tail(max_rows).to_csv(index=False).rstrip()
    if len(frame) <= max_rows:
        return csv
    return f"(showing last {max_rows} of {len(frame)} rows)\n{csv}"


def _blocks(name: str, value: Any, max_rows: int) -> list[str]:
    """One block per citable id of the input `name`, node-level block first."""
    if isinstance(value, pd.DataFrame):
        return [_block(name, _frame_body(value, max_rows))]
    ids = sorted(citable_ids({name: value}) - {name})
    if isinstance(value, BaseModel):
        return [_block(name, _json(value))] + [
            _block(cid, _json(getattr(value, cid.removeprefix(f"{name}."))))
            for cid in ids
        ]
    if isinstance(value, list):
        by_id = {
            f"{name}[{item.id}]": item  # type: ignore[attr-defined]
            for item in value
            if isinstance(item, BaseModel) and getattr(item, "id", None) is not None
        }
        # Items keep their input order; the node-level block summarises the collection.
        header = _block(name, f"{len(value)} items" if by_id else _json(value))
        return [header] + [_block(cid, _json(item)) for cid, item in by_id.items()]
    return [_block(name, _json(value))]


def render_context(
    inputs: Mapping[str, Any],
    depth_notes: Mapping[str, str] | None = None,
    *,
    max_rows: int = 50,
) -> str:
    """Render `inputs` as the prompt's evidence, one block per citable id, ordered by input name.

    Frames show their last `max_rows` rows as CSV (with a truncation note), models and list
    items render as JSON, and unavailable inputs (see `unavailable_inputs`) are announced as
    `NOT AVAILABLE` and are not citable. `depth_notes` (input name -> sentence) tell the model
    how thin an input is; they are appended after the evidence.
    """
    unavailable = unavailable_inputs(inputs)
    parts: list[str] = []
    for name in sorted(inputs):
        value = inputs[name]
        if name in unavailable:
            reason = value.reason if isinstance(value, Absent) else "no data"
            parts.append(f"### {name}: NOT AVAILABLE ({reason})")
        else:
            parts.extend(_blocks(name, value, max_rows))
    if depth_notes:
        parts.append("## Input depth\n" + "\n".join(depth_notes[n] for n in sorted(depth_notes)))
    return "\n\n".join(parts)
