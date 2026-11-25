"""M5 demo gate offline: `runs/m5_price_behaviour.yaml` replayed from the recorded yfinance fixtures."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from alpha_nodes.providers.yfinance.history import YFHistoryPayload
from alpha_nodes.registry import build_registry
from lensgraph import RunConfig, arun
from lensgraph.graph import build_plan
from lensgraph.panel import panel_registry
from lensgraph.plan import NodeKey, RunResult
from lensgraph.sources import FakeClock, build_source_store
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.store.files import FileBlobStore
from lensgraph.types import CandidateRef
from lensgraph.view.build import build_run_view
from lensgraph.view.models import RunView

from .conftest import YF_FIXTURES
from .yf_replay import YFReplay

RUN_YAML = Path(__file__).parents[3] / "runs" / "m5_price_behaviour.yaml"
SYMBOLS = ["BP.L", "HSBA.L", "VOD.L", "ASML.AS", "SAP.DE", "MC.PA", "NESN.SW", "NOVO-B.CO"]
TEN_YEAR = ["SAP.DE", "MC.PA"]
UNKNOWN = "NOSUCH.L"
COMPONENTS = {"momentum", "trend", "trend_slope", "volatility", "drawdown"}
CALC_NODES = {"total_return", "momentum", "trend", "volatility", "drawdown", "price_chart"}

Runner = Callable[..., Any]


def make_config(
    symbols: list[str], thresholds: list[float] | None = None, days: int = 700
) -> RunConfig:
    """The shipped config over `symbols`, with a price lookback that fits the 2-year fixtures."""
    cfg = RunConfig.from_yaml(RUN_YAML)
    nodes = {**cfg.nodes, "prices": {"lookback_days": days}}
    if thresholds is not None:
        nodes["price_behaviour"] = {"thresholds": thresholds}
    return cfg.model_copy(
        update={"candidates": [CandidateRef(id=s) for s in symbols], "nodes": nodes}
    )


@pytest.fixture
def ten_year(replay: YFReplay) -> None:
    """SAP.DE and MC.PA replay their 10-year recordings."""
    for symbol in TEN_YEAR:
        replay.histories[symbol] = YFHistoryPayload.model_validate_json(
            (YF_FIXTURES / f"prices_{symbol}_10y.json").read_text()
        )


@pytest.fixture
def run_once(tmp_path: Path, clock: FakeClock, replay: YFReplay, ten_year: None) -> Runner:
    """Run the config on the fake clock into `tmp_path` (the same store every call)."""

    async def run(
        symbols: list[str] = [*SYMBOLS, UNKNOWN],  # noqa: B006
        thresholds: list[float] | None = None,
        days: int = 700,
    ) -> RunResult:
        cfg = make_config(symbols, thresholds, days)
        assert cfg.sources is not None
        store = build_source_store(
            cfg.sources, tmp_path, FileBlobStore(tmp_path / "blobs"), clock=clock
        )
        try:
            return await arun(
                cfg, build_registry(), store_root=tmp_path, services={"sources": store}
            )
        finally:
            store.close()

    return run


def node_results(result: RunResult, name: str) -> dict[str | None, Any]:
    """The `NodeResult` of node `name` by candidate."""
    return {k.candidate: r for k, r in result.results.items() if k.name == name}


async def test_every_candidate_gets_a_price_behaviour_verdict(run_once: Runner) -> None:
    result = await run_once()
    assert result.status == "ok"
    dossiers = node_results(result, "dossier")
    assert set(dossiers) == {*SYMBOLS, UNKNOWN}
    assert all(r.status == "ok" for r in dossiers.values())
    for symbol in SYMBOLS:
        verdict = result.values[NodeKey(name="price_behaviour", candidate=symbol)]
        assert verdict.status == "ok"
        assert set(verdict.components) == COMPONENTS
    unknown = result.values[NodeKey(name="price_behaviour", candidate=UNKNOWN)]
    assert unknown.status != "ok"


async def test_ten_year_symbols_have_full_windows(run_once: Runner) -> None:
    result = await run_once(TEN_YEAR, days=3653)
    for symbol in TEN_YEAR:
        verdict = result.values[NodeKey(name="price_behaviour", candidate=symbol)]
        assert verdict.status == "ok"
        assert set(verdict.components) == COMPONENTS
        assert result.values[NodeKey(name="drawdown", candidate=symbol)].bars == 3 * 252


async def test_threshold_change_recomputes_only_lens_and_aggregator(
    run_once: Runner, replay: YFReplay
) -> None:
    first = await run_once()
    replay.calls.clear()
    second = await run_once(thresholds=[-0.3, -0.1, 0.1, 0.3])
    assert replay.calls == []
    for key, result in second.results.items():
        if key.name == "price_behaviour":
            assert not result.cache_hit, key  # its params are in the memo key
        elif key.name == "dossier":
            lens = second.results[NodeKey(name="price_behaviour", candidate=key.candidate)]
            changed = (
                lens.output_hash
                != first.results[
                    NodeKey(name="price_behaviour", candidate=key.candidate)
                ].output_hash
            )
            assert result.cache_hit != changed, key  # reruns exactly when its lens verdict changed
        else:
            # Calc nodes are deliberately not memoized (price_calcs docstring): they re-execute
            # but reproduce identical outputs, so nothing upstream of the lens is invalidated.
            assert result.output_hash == first.results[key].output_hash, key
    assert not any(r.cache_hit for k, r in second.results.items() if k.name in CALC_NODES)
    assert any(
        r.output_hash != first.results[k].output_hash
        for k, r in second.results.items()
        if k.name == "dossier"
    )
    # Same thresholds again: the lens and the aggregator are served from the memo cache.
    third = await run_once(thresholds=[-0.3, -0.1, 0.1, 0.3])
    assert all(
        r.cache_hit for k, r in third.results.items() if k.name in ("price_behaviour", "dossier")
    )


@pytest.fixture
async def run_view(run_once: Runner, tmp_path: Path) -> RunView:
    """The `RunView` of a run over the 2-year fixtures."""
    result = await run_once(["BP.L", "SAP.DE"])
    index = DuckDBRunIndex(tmp_path / "index.duckdb")
    try:
        return build_run_view(result.run_id, index, FileBlobStore(tmp_path / "blobs"))
    finally:
        index.close()


def test_report_has_chart_and_metric_cites(run_view: RunView) -> None:
    candidate = next(c for c in run_view.candidates if c.id == "BP.L")
    cited = [
        {cite: run_view.cited[ref] for cite, ref in claim.cites.items() if ref is not None}
        for claim in candidate.claims
    ]
    momentum = next(c for c in cited if "momentum.total_return" in c)
    chart = next(v for cite, v in momentum.items() if cite.startswith("price_chart"))
    assert chart.kind == "chart"
    assert chart.chart is not None and len(chart.chart.x) > 100
    assert momentum["momentum.total_return"].kind == "field"


def test_shipped_m5_config_is_valid() -> None:
    cfg = RunConfig.from_yaml(RUN_YAML)
    ids = [c.id for c in cfg.candidates]
    assert len(ids) == len(set(ids)) == 50
    assert sum(i.endswith(".L") for i in ids) == 20
    assert cfg.panel is not None
    assert cfg.panel.lenses == ["price_behaviour"] and cfg.panel.reviewer is None
    assert cfg.nodes["price_behaviour"]["thresholds"] == [-0.6, -0.2, 0.2, 0.6]
    assert cfg.sources is not None and set(cfg.sources.providers) == {"prices", "profile"}
    registry = panel_registry(cfg.panel, build_registry())
    plan = build_plan(cfg.panel.targets(), registry, cfg.candidates)
    assert {k.name for k in plan.nodes} >= {"prices", "price_behaviour", "dossier", *CALC_NODES}
