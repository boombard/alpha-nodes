"""Record models built outside the graph: exports, reports and the LLM-call ledger.

See documentation/design/core.md, Artifact store and run index, and Reporting. Node
outputs never carry run ids (Principles); these models add them afterwards.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .verdict import Dossier, DossierReview


class DossierRecord(BaseModel):
    """A dossier (and optional review) stamped with the run that produced it, for exports and reports."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    created_at: datetime
    dossier: Dossier
    review: DossierReview | None = None


class LLMCall(BaseModel):
    """One model call, with all its retries, made during a run; stored in the run index.

    Args:
        candidate: the candidate the call was for, or None for run-level calls.
        attempts: calls made including validation retries.
        cost_usd: None when the model has no known price (never guessed).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    candidate: str | None
    node: str
    model: str
    attempts: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


class RunInfo(BaseModel):
    """A run's own record from the run index: its status and (UTC) start and finish times.

    Args:
        status: "running" until the run finishes, then the status it finished with ("ok", ...).
        started_at: when the run started; None only for a run the index never saw start.
        finished_at: None while running.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
