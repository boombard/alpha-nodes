"""Node base classes: the unit of computation in a lensgraph.

A node's params are its pydantic fields; structural metadata are ClassVars. See
documentation/design/core.md, Nodes.
"""

import hashlib
import inspect
from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar

import pandera.pandas as pa
from pydantic import BaseModel, ConfigDict, ValidationError

from .types import (
    CandidateRef,
    ContractViolation,
    Failed,
    GlobalFailure,
    Scope,
    UpstreamFailed,
)

__all__ = [
    "CalcNode",
    "FetchNode",
    "GlobalFailure",
    "Node",
    "NodeContext",
    "TransformNode",
]


class NodeContext(BaseModel):
    """Per-execution context handed to `Node.run`: who is being run, when, and with what services."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    candidate: CandidateRef | None  # None for shared-scope nodes
    as_of: date | None = None  # point-in-time cutoff for data access; None means "live"
    services: dict[str, Any] = {}  # injected dependencies (sources, LLM providers), by name
    input_hashes: dict[str, str] = {}  # content hashes of the resolved inputs, by input name


class Node(BaseModel):
    """Base class of every node. Fields are tunable params (set from run config).

    Class-level metadata (ClassVars) declares the node's place in the graph; the graph
    builder resolves `inputs` into an ExecutionPlan (see documentation/design/core.md, Graph).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: ClassVar[str]  # unique node name; what other nodes reference in `inputs`
    inputs: ClassVar[dict[str, str]] = {}  # run() kwarg name -> upstream node name (required)
    optional_inputs: ClassVar[dict[str, str]] = {}  # as `inputs`; a failed one becomes Absent
    output: ClassVar[Any] = object  # contract: a type, BaseModel subclass or pandera model
    scope: ClassVar[Scope] = "candidate"  # "shared" runs once per run, not per candidate
    version: ClassVar[str] = "1"  # bump to invalidate memoized outputs after a logic change
    resource: ClassVar[str | None] = None  # named concurrency pool (e.g. an LLM provider)
    memoize: ClassVar[bool] = True  # False: always execute (fetch nodes); see Memoization
    hash_source: ClassVar[bool] = True  # include the class source in `code_version()`
    consumes_verdicts: ClassVar[bool] = False  # only aggregators may read lens verdicts

    def run(self, ctx: NodeContext, **inputs: Any) -> Any:
        """Compute the output from resolved inputs. Subclasses implement it (may be `async`)."""
        raise NotImplementedError

    def on_upstream_failure(self, ctx: NodeContext, failure: Failed) -> Any:
        """Called instead of `run` when a required input failed.

        Default re-raises as `UpstreamFailed`; override to recover deliberately (rare).
        """
        raise UpstreamFailed(failure)

    def memo_salt(self, services: Mapping[str, Any]) -> str:
        """Extra memo-key material derived from services (e.g. an LLM model id). Default none."""
        return ""

    def check_inputs(self, **inputs: Any) -> None:
        """Hook for checks stricter than the producer guarantees; raise `ContractViolation`."""
        return

    def validate_output(self, value: Any) -> Any:
        """Check `value` against `output` and return it (pandera may coerce).

        Pandera model: `validate`; pydantic class: isinstance or `model_validate`; other
        type: isinstance. Any failure is re-raised as `ContractViolation` naming the node.
        """
        out = self.output
        try:
            if isinstance(out, type) and issubclass(out, pa.DataFrameModel):
                return out.validate(value)
            if isinstance(out, type) and issubclass(out, BaseModel):
                return value if isinstance(value, out) else out.model_validate(value)
            if not isinstance(value, out):
                raise TypeError(f"expected {getattr(out, "__name__", repr(out))}, got {type(value).__name__}")
            return value
        except (AttributeError, TypeError, ValueError, ValidationError, pa.errors.SchemaError) as exc:
            raise ContractViolation(f"{self.name}: output contract violated: {exc}") from exc

    @classmethod
    def code_version(cls) -> str:
        """Short hash of `version` (plus the class source if `hash_source`); a memo key part."""
        material = cls.version
        if cls.hash_source:
            material += inspect.getsource(cls)
        return hashlib.sha256(material.encode()).hexdigest()[:16]

    @classmethod
    def all_inputs(cls) -> dict[str, str]:
        """Required and optional inputs merged: run() kwarg name -> upstream node name."""
        return {**cls.inputs, **cls.optional_inputs}


class FetchNode(Node):
    """Reads from a source store. Never memoized; its output hash keys downstream nodes.

    See documentation/design/core.md, Memoization.
    """

    memoize: ClassVar[bool] = False
    hash_source: ClassVar[bool] = False


class TransformNode(Node):
    """Reshapes or cleans data (ETL). Memoized like any non-fetch node."""


class CalcNode(Node):
    """Deterministic calculation producing derived values from transformed data."""
