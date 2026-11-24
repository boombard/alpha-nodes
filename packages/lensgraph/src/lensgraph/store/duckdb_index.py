"""DuckDB run index: runs, per-node results and the memo table in one local file.

See documentation/design/core.md, Artifact store and run index.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb

from ..plan import ExecutionPlan, NodeKey, NodeResult
from ..plangraph import PlanEdge, PlanGraph, PlanNode
from ..records import LLMCall
from ..types import Failed
from .base import RunIndex

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS runs (
        run_id VARCHAR PRIMARY KEY, config_json VARCHAR,
        started_at TIMESTAMP, finished_at TIMESTAMP, status VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS node_results (
        run_id VARCHAR, node VARCHAR, candidate VARCHAR, status VARCHAR,
        output_hash VARCHAR, memo_key VARCHAR, cache_hit BOOLEAN, error VARCHAR,
        failure_json VARCHAR, duration_s DOUBLE, meta_json VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS llm_calls (
        run_id VARCHAR, candidate VARCHAR, node VARCHAR, model VARCHAR, attempts INTEGER,
        input_tokens BIGINT, output_tokens BIGINT, cost_usd DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS plan_nodes (
        run_id VARCHAR, node VARCHAR, candidate VARCHAR, scope VARCHAR, kind VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS plan_edges (
        run_id VARCHAR, source_node VARCHAR, source_candidate VARCHAR, target_node VARCHAR,
        target_candidate VARCHAR, kwarg VARCHAR, optional BOOLEAN)""",
    """CREATE TABLE IF NOT EXISTS memo (
        memo_key VARCHAR PRIMARY KEY, output_hash VARCHAR, created_at TIMESTAMP)""",
]


class DuckDBRunIndex(RunIndex):
    """RunIndex backed by a DuckDB file.

    Holds one connection, so call it from the event-loop thread only. Call `close()` to
    release the file lock before another instance opens the same path.
    """

    def __init__(self, path: Path) -> None:
        self._con = duckdb.connect(str(path))
        for stmt in _SCHEMA:
            self._con.execute(stmt)

    def close(self) -> None:
        """Close the connection (flushes to disk)."""
        self._con.close()

    def start_run(self, run_id: str, config: Mapping[str, Any]) -> None:
        """Record a new run as "running"; restarting an id discards its old run row and node results."""
        self._con.execute("DELETE FROM runs WHERE run_id = ?", [run_id])
        self._con.execute("DELETE FROM node_results WHERE run_id = ?", [run_id])
        self._con.execute(
            "INSERT INTO runs VALUES (?, ?, now()::TIMESTAMP, NULL, 'running')",
            [run_id, json.dumps(dict(config), default=str)],
        )

    def finish_run(self, run_id: str, status: str) -> None:
        """Stamp the run's finish time and final status."""
        self._con.execute(
            "UPDATE runs SET finished_at = now()::TIMESTAMP, status = ? WHERE run_id = ?",
            [status, run_id],
        )

    def record_node(self, run_id: str, result: NodeResult) -> None:
        """Append one node instance's outcome to the run's audit trail."""
        self._con.execute(
            "INSERT INTO node_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                result.key.name,
                result.key.candidate,
                result.status,
                result.output_hash,
                result.memo_key,
                result.cache_hit,
                result.error,
                result.failure.model_dump_json() if result.failure else None,
                result.duration_s,
                json.dumps(result.meta),
            ],
        )

    def lookup_memo(self, memo_key: str) -> str | None:
        """Output hash last saved for `memo_key`, or None."""
        row = self._con.execute(
            "SELECT output_hash FROM memo WHERE memo_key = ?", [memo_key]
        ).fetchone()
        return row[0] if row else None

    def save_memo(self, memo_key: str, output_hash: str) -> None:
        """Upsert the memo entry; the latest write wins."""
        self._con.execute(
            "INSERT OR REPLACE INTO memo VALUES (?, ?, now()::TIMESTAMP)", [memo_key, output_hash]
        )

    def node_results(self, run_id: str) -> list[NodeResult]:
        """The run's node results in the order they were recorded."""
        rows = self._con.execute(
            "SELECT node, candidate, status, output_hash, memo_key, cache_hit, error,"
            " failure_json, duration_s, meta_json FROM node_results"
            " WHERE run_id = ? ORDER BY rowid",
            [run_id],
        ).fetchall()
        return [
            NodeResult(
                key=NodeKey(name=node, candidate=candidate),
                status=status,
                output_hash=output_hash,
                memo_key=memo_key,
                cache_hit=cache_hit,
                error=error,
                failure=Failed.model_validate_json(failure_json) if failure_json else None,
                duration_s=duration_s,
                meta=json.loads(meta_json),
            )
            for (node, candidate, status, output_hash, memo_key, cache_hit, error,
                 failure_json, duration_s, meta_json) in rows
        ]

    def record_llm_call(self, call: LLMCall) -> None:
        """Append one model call to the run's cost ledger."""
        self._con.execute(
            "INSERT INTO llm_calls VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [call.run_id, call.candidate, call.node, call.model, call.attempts,
             call.input_tokens, call.output_tokens, call.cost_usd],
        )

    def llm_calls(self, run_id: str) -> list[LLMCall]:
        """The run's recorded model calls in insertion order."""
        rows = self._con.execute(
            "SELECT run_id, candidate, node, model, attempts, input_tokens, output_tokens,"
            " cost_usd FROM llm_calls WHERE run_id = ? ORDER BY rowid",
            [run_id],
        ).fetchall()
        return [
            LLMCall(run_id=r[0], candidate=r[1], node=r[2], model=r[3], attempts=r[4],
                    input_tokens=r[5], output_tokens=r[6], cost_usd=r[7])
            for r in rows
        ]

    def run_config(self, run_id: str) -> dict[str, Any]:
        """The config the run was started with; KeyError for an unknown run."""
        row = self._con.execute(
            "SELECT config_json FROM runs WHERE run_id = ?", [run_id]
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def node_result(self, run_id: str, node: str, candidate: str | None) -> NodeResult | None:
        """The first recorded result for a node instance in the run, or None."""
        match = [r for r in self.node_results(run_id)
                 if r.key.name == node and r.key.candidate == candidate]
        return match[0] if match else None

    def record_plan(self, run_id: str, plan: ExecutionPlan) -> None:
        """Persist the plan's nodes and edges (replacing any earlier plan for the run id)."""
        graph = PlanGraph.from_plan(plan)
        self._con.execute("DELETE FROM plan_nodes WHERE run_id = ?", [run_id])
        self._con.execute("DELETE FROM plan_edges WHERE run_id = ?", [run_id])
        for n in graph.nodes:
            self._con.execute(
                "INSERT INTO plan_nodes VALUES (?, ?, ?, ?, ?)",
                [run_id, n.key.name, n.key.candidate, n.scope, n.kind],
            )
        for e in graph.edges:
            self._con.execute(
                "INSERT INTO plan_edges VALUES (?, ?, ?, ?, ?, ?, ?)",
                [run_id, e.source.name, e.source.candidate, e.target.name, e.target.candidate,
                 e.kwarg, e.optional],
            )

    def plan_graph(self, run_id: str) -> PlanGraph:
        """The plan recorded for the run, in plan order (empty graph if none was recorded)."""
        nodes = self._con.execute(
            "SELECT node, candidate, scope, kind FROM plan_nodes WHERE run_id = ? ORDER BY rowid",
            [run_id],
        ).fetchall()
        edges = self._con.execute(
            "SELECT source_node, source_candidate, target_node, target_candidate, kwarg, optional"
            " FROM plan_edges WHERE run_id = ? ORDER BY rowid",
            [run_id],
        ).fetchall()
        return PlanGraph(
            nodes=[PlanNode(key=NodeKey(name=n, candidate=c), scope=s, kind=k)
                   for n, c, s, k in nodes],
            edges=[PlanEdge(source=NodeKey(name=sn, candidate=sc),
                            target=NodeKey(name=tn, candidate=tc), kwarg=kw, optional=o)
                   for sn, sc, tn, tc, kw, o in edges],
        )
