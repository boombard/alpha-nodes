"""M6 demo gate offline: `runs/m6_fundamentals.yaml` replayed from the recorded yfinance and EDGAR fixtures.

The AI lenses answer through a counting `FunctionModel` that cites ids it finds in the prompt.
"""

import importlib.util
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import pydantic_ai.models
import pytest
from alpha_nodes.registry import build_registry
from lensgraph import RunConfig, arun
from lensgraph.graph import build_plan
from lensgraph.llm import LLMProfile, ProfileRegistry
from lensgraph.panel import panel_registry
from lensgraph.plan import NodeKey, RunResult
from lensgraph.sources import FakeClock, build_source_store
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.store.files import FileBlobStore
from lensgraph.types import CandidateRef
from lensgraph.view.build import build_run_view
from lensgraph.view.models import RunView
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .edgar_replay import EdgarReplay

ROOT = Path(__file__).parents[3]
RUN_YAML = ROOT / "runs" / "m6_fundamentals.yaml"
COMPARE_SCRIPT = ROOT / "packages" / "alpha_nodes" / "scripts" / "compare_variants.py"
SYMBOLS = ["AAPL", "BP.L", "HSBA.L", "BOOT.L", "ASML.AS", "SAP.DE", "NESN.SW", "NOVO-B.CO"]
UNKNOWN = "NOSUCH.L"
LENSES = ["price_behaviour", "quality_value", "price_vs_fundamentals"]
PREFERRED_CITES = ("profitability.roe_mean", "momentum.total_return")

Runner = Callable[..., Any]


class CountingModel(FunctionModel):
    """Answers every AI lens call with a valid verdict citing ids from the prompt; counts the calls."""

    def __init__(self) -> None:
        self.calls = 0
        super().__init__(self._answer)

    def _answer(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.calls += 1
        parts = [p for m in messages if isinstance(m, ModelRequest) for p in m.parts]
        system = "\n".join(str(p.content) for p in parts if isinstance(p, SystemPromptPart))
        user = "\n".join(str(p.content) for p in parts if isinstance(p, UserPromptPart))
        ids = re.findall(r"^### \[(.+)\]$", user, flags=re.MULTILINE)
        field = next((c for c in PREFERRED_CITES if c in ids), next(i for i in ids if "." in i))
        cites = [field, *[i for i in ids if i.startswith("recent_news[")][:1]]
        payload = {
            "status": "ok",
            "stance": 2 if "Warren Buffett" in system else 1,
            "conviction": "medium",
            "claims": [{"text": "Evidence supports the view", "direction": 1, "cites": cites}],
            "flags": [],
        }
        if info.output_tools:
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])
        return ModelResponse(parts=[TextPart(json.dumps(payload))])


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No real model request; the EDGAR provider has a User-Agent."""
    monkeypatch.setattr(pydantic_ai.models, "ALLOW_MODEL_REQUESTS", False)
    monkeypatch.setenv("ALPHA_NODES_SEC_USER_AGENT", "Test Suite test@example.test")


@pytest.fixture
def model() -> CountingModel:
    """The counting stand-in LLM shared by every run of a test."""
    return CountingModel()


@pytest.fixture
def run_once(
    tmp_path: Path, clock: FakeClock, replay: Any, edgar_replay: EdgarReplay, model: CountingModel
) -> Runner:
    """Run the shipped config on the fake clock into `tmp_path` (the same store every call)."""
    profiles = ProfileRegistry(
        {"dev": LLMProfile(name="dev", model="test")}, model_overrides={"dev": model}
    )

    async def run(
        symbols: list[str] = [*SYMBOLS, UNKNOWN],  # noqa: B006
        variant: str | None = None,
    ) -> RunResult:
        cfg = RunConfig.from_yaml(RUN_YAML)
        nodes: dict[str, Any] = {**cfg.nodes, "prices": {"lookback_days": 700}}
        if variant:
            nodes["quality_value"] = {"variant": variant}
        cfg = cfg.model_copy(
            update={"candidates": [CandidateRef(id=s) for s in symbols], "nodes": nodes}
        )
        assert cfg.sources is not None
        store = build_source_store(
            cfg.sources, tmp_path, FileBlobStore(tmp_path / "blobs"), clock=clock
        )
        try:
            return await arun(
                cfg,
                build_registry(),
                store_root=tmp_path,
                services={"sources": store, "profiles": profiles},
            )
        finally:
            store.close()

    return run


def verdict(result: RunResult, lens: str, symbol: str) -> Any:
    """The lens verdict of `symbol`."""
    return result.values[NodeKey(name=lens, candidate=symbol)]


async def test_every_candidate_gets_three_verdicts(run_once: Runner, tmp_path: Path) -> None:
    result = await run_once()
    assert result.status == "ok"
    for symbol in SYMBOLS:
        dossier = result.values[NodeKey(name="dossier", candidate=symbol)]
        assert sorted(v.lens for v in dossier.verdicts) == sorted(LENSES)
        assert all(v.status == "ok" for v in dossier.verdicts), (
            symbol,
            [(v.lens, v.status, (v.error or "")[:140]) for v in dossier.verdicts],
        )
    con = duckdb.connect(str(tmp_path / "sources.duckdb"), read_only=True)
    try:
        providers = dict(
            con.execute(
                "SELECT entity, any_value(provider) FROM facts_fundamentals GROUP BY entity"
            ).fetchall()
        )
    finally:
        con.close()
    assert providers["AAPL"] == "edgar"
    assert providers["BP.L"] == "yfinance"


async def test_uk_european_coverage_lower_than_us(run_once: Runner) -> None:
    result = await run_once(["AAPL", "BP.L"])
    us, uk = (verdict(result, "quality_value", s) for s in ("AAPL", "BP.L"))
    assert uk.coverage < us.coverage
    assert result.values[NodeKey(name="dossier", candidate="BP.L")].confidence < (
        result.values[NodeKey(name="dossier", candidate="AAPL")].confidence
    )
    assert len(result.values[NodeKey(name="annual_fundamentals", candidate="AAPL")]) >= 8
    assert len(result.values[NodeKey(name="annual_fundamentals", candidate="BP.L")]) <= 5


async def test_bank_runs_without_operating_items(run_once: Runner) -> None:
    result = await run_once(["HSBA.L"])
    for lens in LENSES:
        assert verdict(result, lens, "HSBA.L").status in ("ok", "abstained"), lens
    assert verdict(result, "quality_value", "HSBA.L").status != "failed"


async def test_unknown_ticker_abstains_without_llm_calls(
    run_once: Runner, model: CountingModel
) -> None:
    result = await run_once([UNKNOWN])
    for lens in ("quality_value", "price_vs_fundamentals"):
        v = verdict(result, lens, UNKNOWN)
        assert v.status == "abstained"
        assert "annual_fundamentals" in (v.error or "")
    assert model.calls == 0


async def test_variant_change_reruns_only_quality_value_and_dossier(
    run_once: Runner, model: CountingModel, replay: Any, edgar_replay: EdgarReplay
) -> None:
    first = await run_once()
    replay.calls.clear()
    edgar_replay.requests.clear()
    model.calls = 0
    second = await run_once(variant="buffett_persona")
    assert replay.calls == [] and edgar_replay.requests == []
    assert model.calls == len(SYMBOLS)  # one quality_value call per candidate with fundamentals
    for key, result in second.results.items():
        if key.name in ("quality_value", "dossier") and key.candidate != UNKNOWN:
            assert not result.cache_hit, key
        elif key.name in ("price_behaviour", "price_vs_fundamentals"):
            assert result.cache_hit, key
        if key.name not in ("quality_value", "dossier"):
            assert result.output_hash == first.results[key].output_hash, key


@pytest.fixture
async def run_view(run_once: Runner, tmp_path: Path) -> RunView:
    """The `RunView` of a run over AAPL."""
    result = await run_once(["AAPL"])
    index = DuckDBRunIndex(tmp_path / "index.duckdb")
    try:
        return build_run_view(result.run_id, index, FileBlobStore(tmp_path / "blobs"))
    finally:
        index.close()


def test_report_resolves_ai_cites(run_view: RunView) -> None:
    candidate = run_view.candidates[0]
    claim = next(c for c in candidate.claims if c.lens == "quality_value")
    resolved = {cite: run_view.cited[ref] for cite, ref in claim.cites.items() if ref is not None}
    assert resolved["profitability.roe_mean"].kind == "field"
    news = next(v for cite, v in resolved.items() if cite.startswith("recent_news["))
    assert news.kind == "item"


async def test_compare_variants_on_two_runs(run_once: Runner, tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("compare_variants", COMPARE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_a = await run_once(SYMBOLS)
    run_b = await run_once(SYMBOLS, variant="buffett_persona")
    comparison = module.compare(tmp_path, run_a.run_id, run_b.run_id)
    assert [r.candidate for r in comparison.rows] == sorted(SYMBOLS)
    assert 0.0 <= comparison.agreement_exact <= comparison.agreement_within_1 <= 1.0
    assert comparison.mean_abs_difference == 1.0  # the stub says 1 for the rubric and 2 for the persona
    assert comparison.cites_per_input_a["profitability"] == len(SYMBOLS)
    assert "stance agreement" in comparison.render()


def test_shipped_m6_config_is_valid() -> None:
    cfg = RunConfig.from_yaml(RUN_YAML)
    ids = [c.id for c in cfg.candidates]
    assert len(ids) == len(set(ids)) == 15
    assert sum(i.endswith(".L") for i in ids) == 5
    assert cfg.panel is not None and cfg.panel.lenses == LENSES and cfg.panel.reviewer is None
    assert not any("profile" in params for params in cfg.nodes.values())  # AI lenses stay on `dev`
    assert "profile:" not in RUN_YAML.read_text().replace("    profile: [yfinance]", "")
    assert cfg.sources is not None
    assert set(cfg.sources.providers) == {"prices", "profile", "fx", "news", "fundamentals"}
    assert cfg.sources.providers["fundamentals"] == ["edgar", "yfinance"]
    registry = panel_registry(cfg.panel, build_registry())
    plan = build_plan(cfg.panel.targets(), registry, cfg.candidates)
    assert {k.name for k in plan.nodes} >= {"fundamentals", "news", "fx", "valuation", *LENSES}
