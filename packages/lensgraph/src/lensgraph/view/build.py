"""Build `RunView` from a run index and blob store, and write it as `run.json` / `data/run.js`.

See documentation/design/core.md, Reporting: run view. The view is derived only from the index
and blobs, so a finished run can be reported on without re-running anything, and the output is
deterministic (sorted keys, stable ordering) so it can be diffed and snapshotted.
"""

import json
import math
from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, get_args

import numpy as np
import pandas as pd
from pydantic import BaseModel

from ..charts import LineChart
from ..lineage import CitedValue, UnresolvedCitation, resolve_citation
from ..plan import NodeResult, NodeStatus
from ..records import DossierRecord
from ..store.base import BlobStore, RunIndex
from ..units import Unit, format_value, units_for_cite
from ..verdict import Dossier, DossierReview, LensVerdict
from .models import CandidateView, CitedView, ClaimRef, FlagRef, RunSummary, RunView, TableData


def json_safe(value: Any) -> Any:
    """Convert `value` to JSON-native data: no NaN/inf (-> None), ISO datetimes, no numpy types.

    Models become dicts, sets become sorted lists, and anything unknown becomes its `str()`.
    """
    if value is None or isinstance(value, bool | str):
        return value
    if value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime | date):  # pd.Timestamp is a datetime
        return value.isoformat()
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, BaseModel):
        return json_safe(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, set | frozenset):
        return sorted((json_safe(v) for v in value), key=repr)
    if isinstance(value, list | tuple):
        return [json_safe(v) for v in value]
    return str(value)


def _with_display(table: TableData, units: Mapping[str, Unit]) -> TableData:
    """`table` plus the unit ids and formatted cells of the columns that have a unit.

    Each row is the formatting context, so a unit's `prefix_field` finds its sibling column. A
    table with no unit column is returned unchanged (`display_rows` stays None).
    """
    unit_cols = {c: units[c] for c in table.columns if c in units}
    if not unit_cols:
        return table
    display = [
        [
            format_value(v, unit_cols[c], dict(zip(table.columns, row, strict=True)))
            if c in unit_cols and isinstance(v, int | float) and not isinstance(v, bool)
            else None
            for c, v in zip(table.columns, row, strict=True)
        ]
        for row in table.rows
    ]
    return table.model_copy(
        update={"units": {c: u.id for c, u in unit_cols.items()}, "display_rows": display}
    )


def _display_fields(fields: Mapping[str, Any], units: Mapping[str, Unit]) -> dict[str, str] | None:
    """Formatted strings of the numeric `fields` that have a unit (siblings give the prefix)."""
    out: dict[str, str] = {}
    for name, unit in units.items():
        value = fields.get(name)
        if isinstance(value, int | float) and not isinstance(value, bool):
            text = format_value(value, unit, fields)
            if text is not None:
                out[name] = text
    return out or None


def frame_table(frame: pd.DataFrame, *, max_rows: int) -> TableData:
    """A frame as a `TableData` of its last `max_rows` rows; a non-default index becomes columns."""
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    total = len(frame)
    tail = frame.tail(max_rows) if max_rows > 0 else frame.iloc[0:0]
    return TableData(
        columns=[str(c) for c in frame.columns],
        rows=[[json_safe(v) for v in row] for row in tail.itertuples(index=False, name=None)],
        total_rows=total,
        truncated=total > len(tail),
    )


def _models_table(items: list[BaseModel], *, max_rows: int) -> TableData:
    """A list of same-typed models as a table of their JSON fields (last `max_rows`)."""
    columns = list(type(items[0]).model_fields)
    tail = items[-max_rows:] if max_rows > 0 else []
    rows = []
    for item in tail:
        dumped = item.model_dump(mode="json")
        rows.append([json_safe(dumped.get(c)) for c in columns])
    return TableData(
        columns=columns, rows=rows, total_rows=len(items), truncated=len(items) > len(tail)
    )


def _units_for(cite: str, cite_units: Mapping[str, Unit]) -> dict[str, Unit]:
    """Field/column -> unit for `cite` out of a verdict's `cite_units` (`input.field` keys)."""
    return {path.split(".", 1)[1]: u for path, u in units_for_cite(cite, cite_units).items()}


def cited_view(
    cited: CitedValue,
    *,
    max_rows: int,
    cite_units: Mapping[str, Unit] | None = None,
    row: Mapping[str, Any] | None = None,
) -> CitedView:
    """The JSON-safe `CitedView` of a resolved citation (frames and model lists become tables).

    `cite_units` (from the verdict's provenance) adds display strings and table units, formatted
    by `lensgraph.units.format_value` so the UI has no formatter of its own; with none, the view
    is as before. `row` is the cited field's parent model, giving a field its `prefix_field`.
    """
    units = _units_for(cited.cite, cite_units or {})
    value = cited.value
    table: TableData | None = None
    json_value: Any = None
    display: dict[str, str] | None = None
    chart: LineChart | None = None
    if isinstance(value, LineChart):
        chart = value
    elif isinstance(value, pd.DataFrame):
        table = _with_display(frame_table(value, max_rows=max_rows), units)
    elif (
        isinstance(value, list)
        and value
        and all(isinstance(v, BaseModel) and type(v) is type(value[0]) for v in value)
    ):
        table = _with_display(_models_table(value, max_rows=max_rows), units)
    else:
        json_value = json_safe(value)
        if cited.kind == "field":
            name = cited.cite.split(".", 1)[1]
            display = _display_fields({**(row or {}), name: json_value}, units)
        elif isinstance(json_value, dict):
            display = _display_fields(json_value, units)
    return CitedView(
        id=f"{cited.source_hash[:16]}:{cited.cite}",
        cite=cited.cite,
        source_hash=cited.source_hash,
        kind=cited.kind,
        table=table,
        json_value=json_value,
        display=display,
        chart=chart,
    )


def _panel_nodes(config: dict[str, Any]) -> tuple[str | None, bool]:
    """(aggregator node name, whether a reviewer runs) from the stored `RunSpec` config."""
    panel = config.get("panel")
    if not isinstance(panel, dict):
        return None, False
    return panel.get("aggregator", "dossier"), bool(panel.get("reviewer"))


def _output(result: NodeResult | None, blobs: BlobStore) -> Any:
    """The stored output of a node result, or None if it has none or the blob is gone."""
    if result is None or result.output_hash is None:
        return None
    try:
        return blobs.get(result.output_hash)
    except Exception:  # noqa: BLE001  # a missing blob leaves a gap in the view, not an error
        return None


def _parent_row(cited: CitedValue, blobs: BlobStore) -> dict[str, Any] | None:
    """For a single-field cite, its parent model as a dict (the field's `prefix_field` context)."""
    if cited.kind != "field":
        return None
    parent = blobs.get(cited.source_hash)
    return json_safe(parent) if isinstance(parent, BaseModel) else None


def _resolve_cites(
    verdict: LensVerdict,
    cites: list[str],
    blobs: BlobStore,
    cited: dict[str, CitedView],
    max_rows: int,
) -> dict[str, str | None]:
    """Resolve `cites` of `verdict` into the shared `cited` map; unresolvable cites map to None."""
    ids: dict[str, str | None] = {}
    for cite in dict.fromkeys(cites):
        try:
            resolved = resolve_citation(verdict, cite, blobs)
            view = cited_view(
                resolved,
                max_rows=max_rows,
                cite_units=verdict.provenance.cite_units,
                row=_parent_row(resolved, blobs),
            )
        except UnresolvedCitation:
            ids[cite] = None
            continue
        cited.setdefault(view.id, view)
        ids[cite] = view.id
    return ids


def _candidate_view(
    cand: str,
    record: DossierRecord,
    statuses: dict[str, NodeStatus],
    blobs: BlobStore,
    cited: dict[str, CitedView],
    max_rows: int,
) -> CandidateView:
    """Resolve the record's claim and flag citations (adding values to `cited`)."""
    claims: list[ClaimRef] = []
    flags: list[FlagRef] = []
    for verdict in record.dossier.verdicts:
        for i, claim in enumerate(verdict.claims):
            ids = _resolve_cites(verdict, claim.cites, blobs, cited, max_rows)
            claims.append(ClaimRef(lens=verdict.lens, claim_index=i, cites=ids))
        for i, flag in enumerate(verdict.flags):
            ids = _resolve_cites(verdict, flag.cites, blobs, cited, max_rows)
            flags.append(FlagRef(lens=verdict.lens, flag_index=i, cites=ids))
    return CandidateView(id=cand, record=record, claims=claims, flags=flags, node_status=statuses)


def build_run_view(
    run_id: str, index: RunIndex, blobs: BlobStore, *, max_rows: int = 200
) -> RunView:
    """Build the `RunView` of `run_id` from the index and blobs alone.

    `DossierRecord.created_at` is the run's finish time (else its start); a run with neither
    raises `ValueError`. Candidates are those with a stored dossier from the panel's aggregator (named in the run
    config), in plan order, and LLM calls sorted by node and candidate (the index returns completion order,
    which varies). A cite whose blob or field is gone maps to None; frames keep their last
    `max_rows` rows.
    """
    config = index.run_config(run_id)
    info = index.run_info(run_id)
    created_at = info.finished_at or info.started_at
    if created_at is None:
        raise ValueError(f"run {run_id!r} has no start time in the index")
    results = index.node_results(run_id)
    plan = index.plan_graph(run_id)
    # The index returns rows in completion order, which varies run to run; order by identity.
    calls = sorted(
        index.llm_calls(run_id), key=lambda c: (c.node, c.candidate or "", c.model, c.attempts)
    )
    aggregator, has_reviewer = _panel_nodes(config)

    shared: dict[str, NodeStatus] = {
        r.key.name: r.status for r in results if r.key.candidate is None
    }
    by_candidate: dict[str, dict[str, NodeStatus]] = {}
    for r in results:
        if r.key.candidate is not None:
            by_candidate.setdefault(r.key.candidate, {})[r.key.name] = r.status

    cited: dict[str, CitedView] = {}
    candidates: list[CandidateView] = []
    plan_order = list(dict.fromkeys(n.key.candidate for n in plan.nodes if n.key.candidate))
    ordered = sorted(
        by_candidate, key=lambda c: (plan_order.index(c) if c in plan_order else len(plan_order), c)
    )
    for cand in ordered:
        statuses = by_candidate[cand]
        dossier = (
            _output(index.node_result(run_id, aggregator, cand), blobs) if aggregator else None
        )
        if not isinstance(dossier, Dossier):
            continue
        review = _output(index.node_result(run_id, "review", cand), blobs) if has_reviewer else None
        record = DossierRecord(
            run_id=run_id,
            created_at=created_at,
            dossier=dossier,
            review=review if isinstance(review, DossierReview) else None,
        )
        candidates.append(
            _candidate_view(cand, record, {**shared, **statuses}, blobs, cited, max_rows)
        )

    counts = Counter(r.status for r in results)
    costs = [c.cost_usd for c in calls]
    summary = RunSummary(
        run_id=run_id,
        status=info.status,
        started_at=info.started_at,
        finished_at=info.finished_at,
        config=json_safe(config),
        node_counts={s: counts.get(s, 0) for s in get_args(NodeStatus)},
        cache_hits=sum(r.cache_hit for r in results),
        llm_input_tokens=sum(c.input_tokens for c in calls),
        llm_output_tokens=sum(c.output_tokens for c in calls),
        llm_cost_usd=None if None in costs else float(sum(c for c in costs if c is not None)),
    )
    return RunView(
        summary=summary,
        plan=plan,
        candidates=candidates,
        cited=cited,
        llm_calls=calls,
    )


def render_run_json(view: RunView) -> str:
    """The canonical `run.json` text of `view`: sorted keys, NaN as null, trailing newline."""
    data = json.loads(view.model_dump_json())  # pydantic writes NaN/inf as null
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def write_run_view(view: RunView, out_dir: Path) -> Path:
    """Write `out_dir/run.json` (the contract) and `out_dir/data/run.js`; return `run.json`.

    `data/run.js` is `window.__RUN__ = <the same JSON>;`, so the report opens from `file://`,
    where browsers block `fetch` (see core.md, Reporting: data sources).
    """
    out_dir = Path(out_dir)
    text = render_run_json(view)
    path = out_dir / "run.json"
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    (out_dir / "data" / "run.js").write_text(f"window.__RUN__ = {text.rstrip()};\n")
    return path
