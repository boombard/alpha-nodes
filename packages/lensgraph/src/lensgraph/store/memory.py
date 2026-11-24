"""In-memory store backends for tests and ephemeral runs (nothing persists)."""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..plan import ExecutionPlan, NodeResult
from ..plangraph import PlanGraph
from ..records import LLMCall, RunInfo
from .base import RunIndex
from .files import FsspecBlobStore


class InMemoryBlobStore(FsspecBlobStore):
    """FsspecBlobStore on fsspec's `memory://` filesystem, for tests and ephemeral runs.

    Values go through the real encoding, so `get` returns a decoded copy, never the caller's
    object. fsspec's memory filesystem is process-global, so each instance gets a unique root.
    """

    def __init__(self) -> None:
        super().__init__(f"memory://lensgraph-{uuid.uuid4().hex}")


class InMemoryRunIndex(RunIndex):
    """Dict-backed RunIndex. `runs` exposes run records for inspection in tests."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self._memo: dict[str, str] = {}
        self._results: dict[str, list[NodeResult]] = {}
        self._llm_calls: dict[str, list[LLMCall]] = {}
        self._plans: dict[str, PlanGraph] = {}

    def start_run(self, run_id: str, config: Mapping[str, Any]) -> None:
        self.runs[run_id] = {
            "config": dict(config),
            "status": "running",
            "started_at": datetime.now(UTC),
            "finished_at": None,
        }
        self._results[run_id] = []

    def finish_run(self, run_id: str, status: str) -> None:
        run = self.runs.setdefault(run_id, {"config": {}, "started_at": None})
        run["status"] = status
        run["finished_at"] = datetime.now(UTC)

    def record_node(self, run_id: str, result: NodeResult) -> None:
        self._results.setdefault(run_id, []).append(result)

    def lookup_memo(self, memo_key: str) -> str | None:
        return self._memo.get(memo_key)

    def save_memo(self, memo_key: str, output_hash: str) -> None:
        self._memo[memo_key] = output_hash

    def node_results(self, run_id: str) -> list[NodeResult]:
        return list(self._results.get(run_id, []))

    def record_llm_call(self, call: LLMCall) -> None:
        self._llm_calls.setdefault(call.run_id, []).append(call)

    def llm_calls(self, run_id: str) -> list[LLMCall]:
        return list(self._llm_calls.get(run_id, []))

    def run_config(self, run_id: str) -> dict[str, Any]:
        return dict(self.runs[run_id]["config"])

    def node_result(self, run_id: str, node: str, candidate: str | None) -> NodeResult | None:
        return next(
            (r for r in self._results.get(run_id, [])
             if r.key.name == node and r.key.candidate == candidate),
            None,
        )

    def record_plan(self, run_id: str, plan: ExecutionPlan) -> None:
        self._plans[run_id] = PlanGraph.from_plan(plan)

    def plan_graph(self, run_id: str) -> PlanGraph:
        return self._plans[run_id]

    def run_info(self, run_id: str) -> RunInfo:
        run = self.runs[run_id]
        return RunInfo(
            run_id=run_id,
            status=run["status"],
            started_at=run.get("started_at"),
            finished_at=run.get("finished_at"),
        )
