"""Value types and exceptions shared by every layer of lensgraph.

Failure-as-data (`Failed`, `Absent`) and the exceptions that control it are described in
documentation/design/core.md, Failure semantics.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Scope = Literal["shared", "candidate"]
"""Whether a node runs once per run ("shared") or once per candidate ("candidate")."""


class _Frozen(BaseModel):
    """Base for immutable, hashable value models that reject unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class CandidateRef(_Frozen):
    """The thing being assessed (a strain, a stock...). Opaque to the core beyond its id."""

    id: str  # unique within a run; becomes part of every per-candidate NodeKey
    attrs: dict[str, str | int | float | bool | None] = {}


class Absent(_Frozen):
    """Marker for a legitimately missing value, or an optional upstream that failed.

    Distinct from `None` so that "nothing there" is explicit and hashes differently.
    """

    reason: str


class Failed(_Frozen):
    """A node failure recorded as data so downstream nodes can skip or recover.

    See documentation/design/core.md, Failure semantics.
    """

    origin: str  # node where the failure arose
    candidate: str | None
    error: str


class GlobalFailure(Exception):
    """Raised by a node when the whole run cannot continue (e.g. provider outage)."""


class UpstreamFailed(Exception):
    """Raised by the default `Node.on_upstream_failure`; carries the upstream `Failed`."""

    def __init__(self, failure: Failed) -> None:
        super().__init__(f"upstream failed at {failure.origin}: {failure.error}")
        self.failure = failure


class ContractViolation(Exception):
    """A node input or output broke its declared contract (schema, type, required columns)."""
