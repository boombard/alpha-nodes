"""RunView build and export: shape, citation resolution, JSON-safety and determinism."""

import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
import pytest
from lensgraph.aggregate import ShrunkMeanAggregator
from lensgraph.charts import LineChart
from lensgraph.plan import NodeKey, NodeResult
from lensgraph.plangraph import PlanGraph
from lensgraph.records import LLMCall, RunInfo
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.store.memory import InMemoryBlobStore, InMemoryRunIndex
from lensgraph.types import CandidateRef
from lensgraph.units import FRACTION, Unit
from lensgraph.verdict import Claim, Flag, LensVerdict, Provenance
from lensgraph.view.build import build_run_view, render_run_json, write_run_view
from lensgraph.view.models import RunView
from pydantic import BaseModel
from toy.nodes import ToxNote
from toy.toy_view import ToyRun, run_toy_panel


@pytest.fixture
def toy_run(tmp_path: Path) -> ToyRun:
    return run_toy_panel(tmp_path / "store")


@pytest.fixture
def view(toy_run: ToyRun) -> RunView:
    index = toy_run.index()
    try:
        return build_run_view(toy_run.run_id, index, toy_run.blobs())
    finally:
        index.close()


def _build(toy_run: ToyRun, **kwargs) -> RunView:
    index = toy_run.index()
    try:
        return build_run_view(toy_run.run_id, index, toy_run.blobs(), **kwargs)
    finally:
        index.close()


def test_run_view_toy_shape(view: RunView):
    assert [c.id for c in view.candidates] == ["S1", "S2", "S3"]
    s3 = view.candidates[2]
    assert s3.record.dossier.overall_stance is None
    assert all(c.record.review is not None for c in view.candidates)
    assert {n.key.name for n in view.plan.nodes} >= {"dossier", "review", "growth_lens"}
    kinds = {n.key.name: n.kind for n in view.plan.nodes}
    assert kinds["review"] == "reviewer" and kinds["dossier"] == "aggregator"
    assert view.summary.run_id == "toy-run"
    assert view.summary.node_counts["ok"] > 0
    assert view.schema_version == 1
    s1 = view.candidates[0]
    assert s1.node_status["review"] == "ok" and s1.node_status["growth_lens"] == "ok"
    assert "reference" in s1.node_status or "assay_raw" in s1.node_status  # shared/other nodes


def test_cited_values_resolved_and_deduplicated(view: RunView):
    s1 = view.candidates[0]
    growth = next(r for r in s1.claims if r.lens == "growth")
    cid = growth.cites["growth_rate"]
    assert cid is not None
    cited = view.cited[cid]
    assert cited.cite == "growth_rate" and cited.id == cid
    assert cid == f"{cited.source_hash[:16]}:growth_rate"
    assert cited.json_value is not None or cited.table is not None
    assert len(view.cited) == len({c.id for c in view.cited.values()})
    all_ids = [i for c in view.candidates for r in c.claims for i in r.cites.values() if i]
    assert len(all_ids) > len(set(all_ids)) or len(view.cited) == len(set(all_ids))
    assert set(all_ids) == set(view.cited)


def test_unresolved_cite_is_null_not_error(toy_run: ToyRun):
    before = _build(toy_run)
    cid = next(i for i in before.cited if i.endswith(":growth_rate"))
    h = before.cited[cid].source_hash
    for path in (toy_run.root / "blobs").rglob(f"{h}*"):
        path.unlink()
    after = _build(toy_run)
    growth = next(r for r in after.candidates[0].claims if r.lens == "growth")
    assert growth.cites["growth_rate"] is None
    assert cid not in after.cited


def test_frame_truncated_to_max_rows(toy_run: ToyRun):
    full = _build(toy_run, max_rows=200)
    capped = _build(toy_run, max_rows=3)
    tables = [c.table for c in capped.cited.values() if c.table and c.kind == "frame"]
    full_tables = [c.table for c in full.cited.values() if c.table and c.kind == "frame"]
    if tables:  # the toy safety lens cites model/item values; frames only if a lens cites one
        assert all(len(t.rows) <= 3 for t in tables)
    assert all(not t.truncated and len(t.rows) == t.total_rows for t in full_tables)


def test_frame_table_keeps_last_rows_and_flags_truncation():
    from lensgraph.view.build import frame_table

    frame = pd.DataFrame({"x": range(10), "y": [float("nan")] * 10})
    table = frame_table(frame, max_rows=4)
    assert table.total_rows == 10 and table.truncated
    assert [r[0] for r in table.rows] == [6, 7, 8, 9]
    assert table.columns == ["x", "y"]
    assert all(r[1] is None for r in table.rows)  # NaN is not JSON
    small = frame_table(frame, max_rows=10)
    assert not small.truncated and len(small.rows) == 10


def test_json_safe_values():
    from lensgraph.view.build import json_safe

    ts = pd.Timestamp("2026-01-02T03:04:05", tz="UTC")
    out = json_safe({"a": math.inf, "b": float("nan"), "t": ts, "n": pd.NaT, "l": [1.5, (2, 3)]})
    assert out == {"a": None, "b": None, "t": ts.isoformat(), "n": None, "l": [1.5, [2, 3]]}
    json.dumps(out, allow_nan=False)


def test_llm_cost_none_when_any_unknown(toy_run: ToyRun):
    index = toy_run.index()
    try:
        base = _build(toy_run).summary
        call = LLMCall(
            run_id=toy_run.run_id,
            candidate=None,
            node="x",
            model="mystery:model",
            attempts=1,
            input_tokens=5,
            output_tokens=7,
            cost_usd=None,
        )
        index.record_llm_call(call)
        index.record_llm_call(call.model_copy(update={"cost_usd": 0.5}))
        summary = build_run_view(toy_run.run_id, index, toy_run.blobs()).summary
    finally:
        index.close()
    assert summary.llm_cost_usd is None
    assert summary.llm_input_tokens == base.llm_input_tokens + 10
    assert summary.llm_output_tokens == base.llm_output_tokens + 14


def test_llm_cost_summed_when_all_known(toy_run: ToyRun):
    index = toy_run.index()
    try:
        for cost in (0.25, 0.5):
            index.record_llm_call(
                LLMCall(
                    run_id=toy_run.run_id,
                    candidate=None,
                    node="x",
                    model="m",
                    attempts=1,
                    input_tokens=1,
                    output_tokens=1,
                    cost_usd=cost,
                )
            )
        view = build_run_view(toy_run.run_id, index, toy_run.blobs())
    finally:
        index.close()
    known = [c.cost_usd for c in view.llm_calls]
    if None not in known:
        assert view.summary.llm_cost_usd == pytest.approx(sum(known))  # type: ignore[arg-type]
    else:
        assert view.summary.llm_cost_usd is None


def test_run_json_deterministic(toy_run: ToyRun, tmp_path: Path):
    a = write_run_view(_build(toy_run), tmp_path / "a")
    b = write_run_view(_build(toy_run), tmp_path / "b")
    assert a.name == "run.json" and a.read_bytes() == b.read_bytes()
    data = json.loads(a.read_text())
    assert data["schema_version"] == 1
    assert list(data) == sorted(data)  # sorted keys


def test_run_js_matches_run_json(toy_run: ToyRun, tmp_path: Path):
    path = write_run_view(_build(toy_run), tmp_path / "out")
    js = (tmp_path / "out" / "data" / "run.js").read_text()
    prefix, suffix = "window.__RUN__ = ", ";\n"
    assert js.startswith(prefix) and js.endswith(suffix)
    assert json.loads(js[len(prefix) : -len(suffix)]) == json.loads(path.read_text())
    RunView.model_validate_json(path.read_text())  # the file satisfies the contract


def test_separate_runs_give_identical_run_json(toy_run: ToyRun, tmp_path: Path):
    """Concurrent execution reorders index rows; the view must not depend on that."""
    other = run_toy_panel(tmp_path / "other")
    assert render_run_json(_build(toy_run)) == render_run_json(_build(other))


def test_summary_and_record_times_come_from_run_info(toy_run: ToyRun, view: RunView):
    index = toy_run.index()
    try:
        info = index.run_info(toy_run.run_id)
    finally:
        index.close()
    assert view.summary.status == info.status == "ok"
    assert view.summary.started_at == info.started_at and view.summary.finished_at == info.finished_at
    assert info.finished_at is not None
    assert {c.record.created_at for c in view.candidates} == {info.finished_at}


class _InfoIndex(DuckDBRunIndex):
    """A real index whose `run_info` is overridden, to test the created_at fallbacks."""

    info: RunInfo

    def run_info(self, run_id: str) -> RunInfo:
        return self.info


def _build_with_info(toy_run: ToyRun, **times: datetime | None) -> RunView:
    index = _InfoIndex(toy_run.root / "index.duckdb")
    index.info = RunInfo(run_id=toy_run.run_id, status="running", **times)  # type: ignore[arg-type]
    try:
        return build_run_view(toy_run.run_id, index, toy_run.blobs())
    finally:
        index.close()


def test_created_at_falls_back_to_started_at(toy_run: ToyRun):
    started = datetime(2026, 1, 1, tzinfo=UTC)
    view = _build_with_info(toy_run, started_at=started, finished_at=None)
    assert {c.record.created_at for c in view.candidates} == {started}
    assert view.summary.status == "running" and view.summary.finished_at is None


def test_run_without_any_time_is_an_error(toy_run: ToyRun):
    with pytest.raises(ValueError, match="no start time"):
        _build_with_info(toy_run, started_at=None, finished_at=None)


def test_flag_cites_resolved_into_shared_cited_map():

    blobs, index = InMemoryBlobStore(), InMemoryRunIndex()
    h = blobs.put(0.12)
    verdict = LensVerdict(
        lens="safety", status="ok", stance=1, conviction="high", stance_mean=1.0, coverage=1.0,
        claims=[Claim(text="c", direction=1, cites=["growth_rate"])],
        flags=[
            Flag(severity="warn", code="a", text="t", cites=["growth_rate"]),
            Flag(severity="info", code="b", text="t", cites=["gone"]),
        ],
        provenance=Provenance(lens_version="v", input_hashes={"growth_rate": h}),
    )
    dossier = ShrunkMeanAggregator().combine(CandidateRef(id="S1"), [verdict])
    index.start_run("r", {"panel": {"aggregator": "dossier"}})
    index.finish_run("r", "ok")
    index._plans["r"] = PlanGraph(nodes=[], edges=[])
    index.record_node(
        "r",
        NodeResult(key=NodeKey(name="dossier", candidate="S1"), status="ok", output_hash=blobs.put(dossier)),
    )
    view = build_run_view("r", index, blobs)
    cand = view.candidates[0]
    claim_id = cand.claims[0].cites["growth_rate"]
    assert claim_id is not None and len(view.cited) == 1  # claim and flag share one entry
    assert [(f.lens, f.flag_index) for f in cand.flags] == [("safety", 0), ("safety", 1)]
    assert cand.flags[0].cites == {"growth_rate": claim_id}
    assert cand.flags[1].cites == {"gone": None}
    assert view.summary.status == "ok"


def _view_citing(value, cite: str = "x"):
    """Build a one-candidate run view whose only claim cites `value` as input `x`."""

    blobs, index = InMemoryBlobStore(), InMemoryRunIndex()
    verdict = LensVerdict(
        lens="l", status="ok", stance=1, conviction="high", stance_mean=1.0, coverage=1.0,
        claims=[Claim(text="c", direction=1, cites=[cite])],
        provenance=Provenance(lens_version="v", input_hashes={"x": blobs.put(value)}),
    )
    dossier = ShrunkMeanAggregator().combine(CandidateRef(id="S1"), [verdict])
    index.start_run("r", {"panel": {"aggregator": "dossier"}})
    index.finish_run("r", "ok")
    index._plans["r"] = PlanGraph(nodes=[], edges=[])
    index.record_node(
        "r", NodeResult(key=NodeKey(name="dossier", candidate="S1"), status="ok", output_hash=blobs.put(dossier))
    )
    view = build_run_view("r", index, blobs)
    return next(iter(view.cited.values()))


def test_cited_chart_in_run_view():


    chart = LineChart(
        title="px", x=[date(2024, 1, 1), date(2024, 1, 2)], series={"a": [1.0, None]}, y_label="usd"
    )
    cited = _view_citing(chart)
    assert cited.kind == "chart" and cited.json_value is None and cited.table is None
    assert cited.chart is not None
    dumped = json.loads(cited.model_dump_json())["chart"]
    assert dumped["x"] == ["2024-01-01", "2024-01-02"]
    assert dumped["series"] == {"a": [1.0, None]}


def test_cited_model_unchanged():

    cited = _view_citing(ToxNote(id="n", text="t"))
    assert cited.kind == "model" and cited.json_value == {"id": "n", "text": "t"} and cited.chart is None


# --- cited values shown with their units (core.md, Units; TASK-68) ---

MONEY = Unit(id="money", style="compact", prefix_field="ccy")


class _Metrics(BaseModel):
    """A flat model with a unit-bearing field, a money field prefixed by a sibling, and plain text."""

    roe: Annotated[float | None, FRACTION]
    revenue: Annotated[float, MONEY]
    ccy: str
    name: str


def _view_citing_with_units(value, cite: str, units: dict[str, Unit]):
    """Like `_view_citing`, but the verdict's provenance records `cite_units`."""
    blobs, index = InMemoryBlobStore(), InMemoryRunIndex()
    verdict = LensVerdict(
        lens="l", status="ok", stance=1, conviction="high", stance_mean=1.0, coverage=1.0,
        claims=[Claim(text="c", direction=1, cites=[cite])],
        provenance=Provenance(lens_version="v", input_hashes={"x": blobs.put(value)}, cite_units=units),
    )
    dossier = ShrunkMeanAggregator().combine(CandidateRef(id="S1"), [verdict])
    index.start_run("r", {"panel": {"aggregator": "dossier"}})
    index.finish_run("r", "ok")
    index._plans["r"] = PlanGraph(nodes=[], edges=[])
    index.record_node(
        "r", NodeResult(key=NodeKey(name="dossier", candidate="S1"), status="ok", output_hash=blobs.put(dossier))
    )
    return next(iter(build_run_view("r", index, blobs).cited.values()))


def test_cited_field_has_display():
    cited = _view_citing_with_units(
        _Metrics(roe=0.153, revenue=12.3e9, ccy="USD", name="n"), "x",
        {"x.roe": FRACTION, "x.revenue": MONEY},
    )
    assert cited.display == {"roe": "15.3%", "revenue": "USD 12.3bn"}  # money takes its row prefix
    assert cited.json_value["roe"] == 0.153  # raw values stay


def test_cited_single_field_has_display():
    cited = _view_citing_with_units(
        _Metrics(roe=0.153, revenue=1.0, ccy="USD", name="n"), "x.roe", {"x.roe": FRACTION}
    )
    assert cited.display == {"roe": "15.3%"} and cited.json_value == 0.153


def test_cited_frame_display_rows_and_units():
    frame = pd.DataFrame({"date": ["d1", "d2"], "ret": [0.0123, None], "ccy": ["USD", "USD"]})
    cited = _view_citing_with_units(frame, "x", {"x.ret": FRACTION})
    assert cited.table is not None
    assert cited.table.units == {"ret": "fraction"}
    assert cited.table.display_rows == [[None, "1.23%", None], [None, None, None]]
    assert cited.table.rows[0][1] == 0.0123  # raw values stay for sorting


def test_money_display_uses_row_prefix():
    frame = pd.DataFrame({"revenue": [12.3e9, 4.5e6], "ccy": ["USD", "EUR"]})
    cited = _view_citing_with_units(frame, "x", {"x.revenue": MONEY})
    assert cited.table is not None
    assert [r[0] for r in cited.table.display_rows or []] == ["USD 12.3bn", "EUR 4.5m"]


def test_cite_without_units_has_no_display():
    model = _view_citing(_Metrics(roe=0.1, revenue=1.0, ccy="USD", name="n"))
    frame = _view_citing(pd.DataFrame({"a": [1.0]}))
    assert model.display is None
    assert frame.table is not None and frame.table.units == {} and frame.table.display_rows is None


def test_single_field_money_cite_takes_prefix_from_parent_row():
    cited = _view_citing_with_units(
        _Metrics(roe=0.1, revenue=12.3e9, ccy="USD", name="n"), "x.revenue", {"x.revenue": MONEY}
    )
    assert cited.display == {"revenue": "USD 12.3bn"}


class _Item(BaseModel):
    """An id-bearing model, so `x[<id>]` resolves."""

    id: str
    revenue: Annotated[float, MONEY]
    ccy: str


_ITEMS = [_Item(id="a", revenue=12.3e9, ccy="USD"), _Item(id="b", revenue=4.5e6, ccy="EUR")]


def test_item_cite_has_display():
    cited = _view_citing_with_units(_ITEMS, "x[b]", {"x.revenue": MONEY})
    assert cited.kind == "item" and cited.display == {"revenue": "EUR 4.5m"}


def test_list_of_models_cite_has_units_and_row_prefixed_display_rows():
    cited = _view_citing_with_units(_ITEMS, "x", {"x.revenue": MONEY})
    assert cited.table is not None and cited.table.units == {"revenue": "money"}
    assert cited.table.display_rows == [[None, "USD 12.3bn", None], [None, "EUR 4.5m", None]]
