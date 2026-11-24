from pathlib import Path

import pytest
from lensgraph.plan import NodeKey, NodeResult
from lensgraph.records import LLMCall
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.types import Failed


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "index.duckdb"


def _ok(name: str = "a", candidate: str | None = None) -> NodeResult:
    return NodeResult(key=NodeKey(name=name, candidate=candidate), status="ok", output_hash="h")


def test_index_persistence_across_instances(db_path: Path) -> None:
    index = DuckDBRunIndex(db_path)
    index.start_run("r1", {"cfg": 1})
    index.record_node("r1", _ok())
    index.save_memo("k", "h")
    index.finish_run("r1", "ok")
    index.close()

    reopened = DuckDBRunIndex(db_path)
    assert reopened.node_results("r1") == [_ok()]
    assert reopened.lookup_memo("k") == "h"
    assert reopened.lookup_memo("missing") is None


def test_memo_upsert_latest_wins(db_path: Path) -> None:
    index = DuckDBRunIndex(db_path)
    index.save_memo("k", "h1")
    index.save_memo("k", "h2")
    assert index.lookup_memo("k") == "h2"


def test_node_results_roundtrip(db_path: Path) -> None:
    index = DuckDBRunIndex(db_path)
    index.start_run("r1", {})
    failed = NodeResult(
        key=NodeKey(name="b", candidate="S1"),
        status="failed",
        memo_key="mk",
        cache_hit=True,
        error="boom",
        failure=Failed(origin="b", candidate="S1", error="boom"),
        duration_s=1.25,
        meta={"tokens": 12, "nested": {"x": [1, 2]}},
    )
    results = [_ok("a"), failed]
    for r in results:
        index.record_node("r1", r)
    assert index.node_results("r1") == results
    assert index.node_results("other") == []


def test_run_records_status(db_path: Path) -> None:
    index = DuckDBRunIndex(db_path)
    index.start_run("r1", {"a": 1})
    index.finish_run("r1", "aborted")
    row = index._con.execute("select status, finished_at is not null from runs").fetchone()  # pyright: ignore[reportPrivateUsage]
    assert row == ("aborted", True)


def test_restarting_run_discards_old_node_results(db_path: Path) -> None:
    index = DuckDBRunIndex(db_path)
    index.start_run("r1", {})
    index.record_node("r1", _ok("first"))
    index.start_run("r1", {})
    index.record_node("r1", _ok("second"))
    assert index.node_results("r1") == [_ok("second")]


def test_llm_calls_roundtrip(db_path: Path) -> None:
    index = DuckDBRunIndex(db_path)
    a = LLMCall(run_id="r1", candidate="S1", node="x", model="m:n", attempts=2,
                input_tokens=10, output_tokens=5, cost_usd=0.01)
    b = LLMCall(run_id="r1", candidate=None, node="y", model="m:n", attempts=1,
                input_tokens=1, output_tokens=1, cost_usd=None)
    other = a.model_copy(update={"run_id": "r2"})
    for call in (a, b, other):
        index.record_llm_call(call)
    assert index.llm_calls("r1") == [a, b]
    assert index.llm_calls("none") == []


def test_run_config_roundtrip(db_path: Path) -> None:
    index = DuckDBRunIndex(db_path)
    index.start_run("r1", {"targets": ["a"], "nested": {"x": [1, 2]}})
    assert index.run_config("r1") == {"targets": ["a"], "nested": {"x": [1, 2]}}
    with pytest.raises(KeyError):
        index.run_config("missing")


def test_node_result_lookup(db_path: Path) -> None:
    index = DuckDBRunIndex(db_path)
    index.start_run("r1", {})
    index.record_node("r1", _ok("a", "S1"))
    index.record_node("r1", _ok("a", None))
    assert index.node_result("r1", "a", "S1") == _ok("a", "S1")
    assert index.node_result("r1", "a", None) == _ok("a", None)
    assert index.node_result("r1", "a", "S2") is None
    assert index.node_result("r2", "a", "S1") is None


def test_run_info_lifecycle(db_path: Path) -> None:
    from lensgraph.records import RunInfo

    index = DuckDBRunIndex(db_path)
    index.start_run("r1", {})
    running = index.run_info("r1")
    assert isinstance(running, RunInfo) and running.status == "running"
    assert running.started_at is not None and running.started_at.utcoffset() is not None
    assert running.finished_at is None
    index.finish_run("r1", "ok")
    done = index.run_info("r1")
    assert done.status == "ok" and done.started_at == running.started_at
    assert done.finished_at is not None and done.started_at is not None
    assert done.finished_at >= done.started_at
    with pytest.raises(KeyError):
        index.run_info("nope")
