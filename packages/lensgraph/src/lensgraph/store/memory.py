"""In-memory store backends for tests and ephemeral runs (nothing persists)."""

from collections.abc import Mapping
from typing import Any

from ..hashing import content_hash
from ..plan import NodeResult
from .base import BlobStore, RunIndex


class InMemoryBlobStore(BlobStore):
    """Dict-backed BlobStore holding live objects (no serialization)."""

    def __init__(self) -> None:
        self._blobs: dict[str, Any] = {}

    def put(self, value: Any) -> str:
        h = content_hash(value)
        self._blobs.setdefault(h, value)
        return h

    def get(self, h: str) -> Any:
        return self._blobs[h]

    def has(self, h: str) -> bool:
        return h in self._blobs


class InMemoryRunIndex(RunIndex):
    """Dict-backed RunIndex. `runs` exposes run records for inspection in tests."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self._memo: dict[str, str] = {}
        self._results: dict[str, list[NodeResult]] = {}

    def start_run(self, run_id: str, config: Mapping[str, Any]) -> None:
        self.runs[run_id] = {"config": dict(config), "status": "running"}
        self._results[run_id] = []

    def finish_run(self, run_id: str, status: str) -> None:
        self.runs.setdefault(run_id, {"config": {}})["status"] = status

    def record_node(self, run_id: str, result: NodeResult) -> None:
        self._results.setdefault(run_id, []).append(result)

    def lookup_memo(self, memo_key: str) -> str | None:
        return self._memo.get(memo_key)

    def save_memo(self, memo_key: str, output_hash: str) -> None:
        self._memo[memo_key] = output_hash

    def node_results(self, run_id: str) -> list[NodeResult]:
        return list(self._results.get(run_id, []))
