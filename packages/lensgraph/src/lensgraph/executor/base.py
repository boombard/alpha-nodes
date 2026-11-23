"""Executor protocol and abort exception; see documentation/design/core.md, Execution."""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from typing import Any, Protocol

from ..plan import ExecutionPlan, NodeKey, RunResult
from ..store.base import BlobStore, RunIndex


class Executor(Protocol):
    """Runs an ExecutionPlan to completion against a blob store and run index."""

    async def execute(
        self,
        plan: ExecutionPlan,
        blobs: BlobStore,
        index: RunIndex,
        *,
        services: Mapping[str, Any] | None = None,
        bypass_memo: AbstractSet[NodeKey] = frozenset(),
    ) -> RunResult:
        """Execute `plan`; `bypass_memo` keys are re-run even on a memo hit (forced rerun)."""
        ...


class RunAborted(Exception):
    """Raised when a GlobalFailure aborts a run; carries the partial result and the cause."""

    def __init__(self, result: RunResult, cause: BaseException) -> None:
        super().__init__(f"run {result.run_id} aborted: {cause}")
        self.result = result
        self.cause = cause
