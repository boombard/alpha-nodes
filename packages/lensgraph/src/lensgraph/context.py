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
from .units import Unit, format_value


def unavailable_inputs(inputs: Mapping[str, Any]) -> frozenset[str]:
    """Names of inputs with nothing to show (absent, None or an empty list); never citable."""
    return frozenset(
        n
        for n, v in inputs.items()
        if v is None or isinstance(v, Absent) or (isinstance(v, list | tuple) and not v)
    )


def _unit_fields(name: str, units: Mapping[str, Unit]) -> dict[str, Unit]:
    """The `input.field` -> unit entries of input `name`, keyed by field."""
    return {p.partition(".")[2]: u for p, u in units.items() if p.partition(".")[0] == name}


def _json(value: Any, fields: Mapping[str, Unit] | None = None) -> str:
    """JSON of `value`; fields with a unit in `fields` are replaced by their formatted string."""
    if isinstance(value, BaseModel):
        if not fields or not set(fields) & set(type(value).model_fields):
            return value.model_dump_json()
        row = value.model_dump(mode="json")
        shown = {k: format_value(v, fields[k], row) if k in fields and v is not None else v for k, v in row.items()}
        return json.dumps(shown, default=str)
    return json.dumps(value, default=str)


def _json_list(items: list[Any], fields: Mapping[str, Unit]) -> str:
    """JSON of a list input whose items have no citable ids, unit fields formatted per item."""
    return json.dumps([json.loads(_json(item, fields)) for item in items], default=str)


def _block(cid: str, body: str) -> str:
    return f"### [{cid}]\n{body}"


def _formatted_frame(frame: pd.DataFrame, fields: Mapping[str, Unit]) -> pd.DataFrame:
    """A copy of `frame` whose unit columns hold formatted strings; headers are left unchanged."""
    shown = frame.copy()
    rows = frame.to_dict("records")
    for column, unit in fields.items():
        if column in frame.columns:
            shown[column] = [
                None if pd.isna(row[column]) else format_value(row[column], unit, row) for row in rows
            ]
    return shown


def _frame_body(frame: pd.DataFrame, max_rows: int, fields: Mapping[str, Unit] | None = None) -> str:
    tail = frame.tail(max_rows)
    csv = (_formatted_frame(tail, fields) if fields else tail).to_csv(index=False).rstrip()
    if len(frame) <= max_rows:
        return csv
    return f"(showing last {max_rows} of {len(frame)} rows)\n{csv}"


def _blocks(name: str, value: Any, max_rows: int, fields: Mapping[str, Unit]) -> list[str]:
    """One block per citable id of the input `name`, node-level block first."""
    if isinstance(value, pd.DataFrame):
        return [_block(name, _frame_body(value, max_rows, fields))]
    ids = sorted(citable_ids({name: value}) - {name})
    if isinstance(value, BaseModel):
        return [_block(name, _json(value, fields))] + [
            _block(cid, _json(_field_value(value, cid.removeprefix(f"{name}."), fields)))
            for cid in ids
        ]
    if isinstance(value, list):
        by_id = {
            f"{name}[{item.id}]": item  # type: ignore[attr-defined]
            for item in value
            if isinstance(item, BaseModel) and getattr(item, "id", None) is not None
        }
        # Items keep their input order; the node-level block summarises the collection.
        header = _block(name, f"{len(value)} items" if by_id else _json_list(value, fields))
        return [header] + [_block(cid, _json(item, fields)) for cid, item in by_id.items()]
    return [_block(name, _json(value))]


def _field_value(model: BaseModel, field: str, fields: Mapping[str, Unit]) -> Any:
    """A model field's value for its own `### [input.field]` block: the formatted string if it has a unit."""
    value = getattr(model, field)
    if field in fields and value is not None:
        return format_value(value, fields[field], model.model_dump(mode="json"))
    return value


def render_context(
    inputs: Mapping[str, Any],
    depth_notes: Mapping[str, str] | None = None,
    *,
    max_rows: int = 50,
    units: Mapping[str, Unit] | None = None,
) -> str:
    """Render `inputs` as the prompt's evidence, one block per citable id, ordered by input name.

    Frames show their last `max_rows` rows as CSV (with a truncation note), models and list
    items render as JSON, and unavailable inputs (see `unavailable_inputs`) are announced as
    `NOT AVAILABLE` and are not citable. `depth_notes` (input name -> sentence) tell the model
    how thin an input is; they are appended after the evidence.

    `units` maps `input.field` to its `Unit` (a lens's bound unit map): such model fields and
    frame cells render formatted by `format_value`, headers unchanged, so the model sees "15.3%"
    rather than 0.153 (core.md, Units). Without it, values render raw.
    """
    unavailable = unavailable_inputs(inputs)
    parts: list[str] = []
    for name in sorted(inputs):
        value = inputs[name]
        if name in unavailable:
            reason = value.reason if isinstance(value, Absent) else "no data"
            parts.append(f"### {name}: NOT AVAILABLE ({reason})")
        else:
            parts.extend(_blocks(name, value, max_rows, _unit_fields(name, units or {})))
    if depth_notes:
        parts.append("## Input depth\n" + "\n".join(depth_notes[n] for n in sorted(depth_notes)))
    return "\n\n".join(parts)
