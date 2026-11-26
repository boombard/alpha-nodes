"""The `RunView` contract: everything the run view app (report now, live view later) reads.

See documentation/design/core.md, Reporting: run view (one app, one contract). Python owns
these models; the TypeScript types in `packages/lensgraph-ui` are generated from them
(`view/schema.py`), so the UI cannot silently disagree with the data. All values are JSON-safe.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..charts import LineChart
from ..plan import NodeStatus
from ..plangraph import PlanGraph
from ..records import DossierRecord, LLMCall


class _ViewModel(BaseModel):
    """Base for contract models: immutable, strict, and defaults count as present in the schema
    (so generated TypeScript types make them required)."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", json_schema_serialization_defaults_required=True
    )


class TableData(_ViewModel):
    """A frame (or list of models) as a capped table; `rows` are the last `len(rows)` rows.

    Args:
        total_rows: row count before capping.
        truncated: True if rows were dropped to respect `max_rows`.
        units: column -> `Unit.id`, for columns whose cite recorded a unit (shown in headers).
        display_rows: formatted strings parallel to `rows` (None per cell without a unit or
            value), or None when no column has a unit. The UI shows these and sorts on `rows`.
    """

    columns: list[str]
    rows: list[list[Any]]
    total_rows: int
    truncated: bool
    units: dict[str, str] = {}
    display_rows: list[list[str | None]] | None = None


class CitedView(_ViewModel):
    """A stored value a claim cites, in JSON-safe form.

    Args:
        id: stable, `f"{source_hash[:16]}:{cite}"`; the same blob cited the same way is one entry.
        cite: the citable id as written in the claim.
        source_hash: content hash of the input blob the value came from.
        kind: as `lineage.CitedValue.kind`.
        table: frames and lists of models.
        json_value: models, fields, items and scalars.
        display: model/field/item cites only: field -> its value formatted by the unit the
            verdict recorded in `Provenance.cite_units`; None if no cited field has a unit.
        chart: set iff kind == "chart" (dates serialise as ISO strings, missing y values as null).
    """

    id: str
    cite: str
    source_hash: str
    kind: Literal["frame", "model", "field", "item", "value", "chart"]
    table: TableData | None = None
    json_value: Any = None
    display: dict[str, str] | None = None
    chart: LineChart | None = None


class ClaimRef(_ViewModel):
    """One claim of a candidate's verdict and where its cited data is.

    Args:
        lens: the verdict's lens name.
        claim_index: 0-based index into that verdict's claims.
        cites: cite -> `CitedView.id` in `RunView.cited`, None if it could not be resolved.
    """

    lens: str
    claim_index: int
    cites: dict[str, str | None]


class FlagRef(_ViewModel):
    """One flag of a candidate's verdict and where its cited data is; like `ClaimRef`.

    Args:
        lens: the verdict's lens name.
        flag_index: 0-based index into that verdict's flags.
        cites: cite -> `CitedView.id` in `RunView.cited`, None if it could not be resolved.
    """

    lens: str
    flag_index: int
    cites: dict[str, str | None]


class CandidateView(_ViewModel):
    """One candidate: its dossier record (with review), claim and flag references, node statuses.

    Claim and flag cites name stored inputs and are resolved into `RunView.cited`. The review's
    cites name verdicts, claims and flags (not stored values), so they stay as written in
    `record.review` and are not resolved.

    Args:
        node_status: node name -> status for nodes of this candidate and for shared nodes.
    """

    id: str
    record: DossierRecord
    claims: list[ClaimRef]
    flags: list[FlagRef]
    node_status: dict[str, NodeStatus]


class RunSummary(_ViewModel):
    """Run-level headline numbers.

    Args:
        status: the run's status in the index ("running" until it finishes, then e.g. "ok").
        started_at, finished_at: from the index (UTC); finished_at is None while running.
        llm_cost_usd: None if any call's cost is unknown (never guessed).
    """

    run_id: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    config: dict[str, Any]
    node_counts: dict[NodeStatus, int]
    cache_hits: int
    llm_input_tokens: int
    llm_output_tokens: int
    llm_cost_usd: float | None


class RunView(_ViewModel):
    """The whole run as plain data: serialised as `run.json`, read by the run view app.

    Args:
        cited: every cited value by `CitedView.id`, deduplicated across candidates.
    """

    schema_version: Literal[1] = 1
    summary: RunSummary
    plan: PlanGraph
    candidates: list[CandidateView]
    cited: dict[str, CitedView]
    llm_calls: list[LLMCall]
