"""End-to-end toy scenarios through the public run API (disk-backed stores in tmp_path)."""

from pathlib import Path

import duckdb
import pytest
from lensgraph import RunSpec, run
from lensgraph.executor.base import RunAborted
from lensgraph.graph import ParamsError, build_plan
from lensgraph.plan import NodeKey, RunResult
from lensgraph.registry import NodeRegistry
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.types import CandidateRef
from toy.sources import FakeAssaySource

GROWTH = ["growth_rate", "tox_notes"]


def _spec(candidates: list[CandidateRef], **kwargs) -> RunSpec:
    return RunSpec(targets=GROWTH, candidates=candidates, **kwargs)


def _do(spec, registry, tmp_path: Path, services, **kw) -> RunResult:
    return run(spec, registry, store_root=tmp_path, services=services, **kw)


def test_fresh_run_outputs(toy_registry: NodeRegistry, toy_candidates, toy_services, tmp_path):
    result = _do(_spec(toy_candidates), toy_registry, tmp_path, toy_services)
    assert result.status == "ok"
    for s in ("S1", "S2"):
        assert isinstance(result.values[NodeKey(name="growth_rate", candidate=s)], float)
    s3 = result.results[NodeKey(name="growth_rate", candidate="S3")]
    assert s3.status == "skipped"
    assert s3.failure is not None and s3.failure.origin == "assay_clean"


def test_identical_rerun_all_memoizable_cached(
    toy_registry, toy_candidates, toy_services, tmp_path
):
    spec = _spec(toy_candidates)
    _do(spec, toy_registry, tmp_path, toy_services)
    second = _do(spec, toy_registry, tmp_path, toy_services)
    memoizable = [r for r in second.results.values() if r.status == "ok" and r.memo_key is not None]
    assert memoizable
    assert all(r.cache_hit for r in memoizable)


def test_param_change_reruns_only_descendants(toy_registry, toy_candidates, toy_services, tmp_path):
    _do(_spec(toy_candidates), toy_registry, tmp_path, toy_services)
    spec = _spec(toy_candidates, nodes={"growth_rate": {"window": 3}})
    second = _do(spec, toy_registry, tmp_path, toy_services)
    assert not _cached_ok(second, "growth_rate")
    assert _cached_ok(second, "assay_clean")


def _cached_ok(result: RunResult, name: str) -> bool:
    flags = {r.cache_hit for k, r in result.results.items() if k.name == name and r.status == "ok"}
    assert len(flags) == 1
    return flags.pop()


def test_invalidate_reruns_node_and_descendants(
    toy_registry, toy_candidates, toy_services, tmp_path
):
    _do(_spec(toy_candidates), toy_registry, tmp_path, toy_services)
    second = _do(
        _spec(toy_candidates, invalidate=["assay_clean"]), toy_registry, tmp_path, toy_services
    )
    assert not _cached_ok(second, "assay_clean")
    assert not _cached_ok(second, "growth_rate")
    assert not any(r.cache_hit for k, r in second.results.items() if k.name == "tox_notes")


def test_no_cache_reruns_everything(toy_registry, toy_candidates, toy_services, tmp_path):
    _do(_spec(toy_candidates), toy_registry, tmp_path, toy_services)
    second = _do(_spec(toy_candidates, no_cache=True), toy_registry, tmp_path, toy_services)
    assert not any(r.cache_hit for r in second.results.values())


def test_abort_then_resume_from_cache(
    toy_registry, toy_candidates, toy_source: FakeAssaySource, toy_services, tmp_path
):
    spec = _spec(toy_candidates)
    toy_source.fail_for = {"S2"}
    with pytest.raises(RunAborted) as exc:
        _do(spec, toy_registry, tmp_path, toy_services)
    finished = [
        k
        for k, r in exc.value.result.results.items()
        if r.status == "ok" and r.memo_key is not None
    ]
    toy_source.fail_for = set()
    second = _do(spec, toy_registry, tmp_path, toy_services)
    assert second.status == "ok"
    assert all(second.results[k].cache_hit for k in finished)


def test_results_persisted_in_index(toy_registry, toy_candidates, toy_services, tmp_path):
    spec = _spec(toy_candidates)
    result = _do(spec, toy_registry, tmp_path, toy_services, run_id="run-x")
    plan = build_plan(spec.targets, toy_registry, toy_candidates)
    index = DuckDBRunIndex(tmp_path / "index.duckdb")
    try:
        assert len(index.node_results("run-x")) == len(plan.nodes)
    finally:
        index.close()
    assert result.run_id == "run-x"


def test_public_api_imports():
    from lensgraph import (  # noqa: F401
        Absent,
        CalcNode,
        CandidateRef,
        FetchNode,
        GlobalFailure,
        Node,
        NodeRegistry,
        RunSpec,
        TransformNode,
        arun,
        build_plan,
        run,
    )


def test_unknown_invalidate_name_raises_and_runs_nothing(
    toy_registry, toy_candidates, toy_source, toy_services, tmp_path
):
    spec = _spec(toy_candidates, invalidate=["nope"])
    with pytest.raises(ParamsError, match="nope"):
        _do(spec, toy_registry, tmp_path, toy_services)
    assert toy_source.calls == []


def test_unexpected_error_marks_run_failed(toy_registry, toy_candidates, toy_services, tmp_path):
    class BrokenExecutor:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _do(
            _spec(toy_candidates),
            toy_registry,
            tmp_path,
            toy_services,
            run_id="r-fail",
            executor=BrokenExecutor(),
        )
    con = duckdb.connect(str(tmp_path / "index.duckdb"))
    try:
        rows = con.execute("SELECT status FROM runs WHERE run_id = 'r-fail'").fetchall()
    finally:
        con.close()
    assert rows == [("failed",)]
