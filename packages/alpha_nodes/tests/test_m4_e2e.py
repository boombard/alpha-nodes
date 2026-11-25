"""M4 demo gate offline: `runs/m4_prices.yaml` replayed from the recorded yfinance fixtures."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yfinance as yf
from alpha_nodes.nodes.fetch import FxRates, Prices, Profile
from alpha_nodes.providers.yfinance.history import YFHistoryPayload
from alpha_nodes.registry import build_registry
from click.testing import CliRunner
from lensgraph import RunConfig, arun
from lensgraph.cli import main
from lensgraph.sources import DuckDBSourceStore, FakeClock, build_source_store
from lensgraph.store.files import FileBlobStore
from lensgraph.types import CandidateRef

from .conftest import YF_FIXTURES
from .yf_replay import YFReplay

RUN_YAML = Path(__file__).parents[3] / "runs" / "m4_prices.yaml"
LAST_FIXTURE_DAY = date(2026, 11, 24)
TODAY = date(2026, 11, 25)
SYMBOLS = ["BP.L", "HSBA.L", "VOD.L", "ASML.AS", "SAP.DE", "NESN.SW", "NOVO-B.CO", "AAPL"]
FX_CURRENCIES = {"GBP", "EUR", "CHF", "SEK", "NOK", "DKK", "PLN"}

Runner = Callable[..., Any]


@pytest.fixture
def replay(monkeypatch: pytest.MonkeyPatch) -> Iterator[YFReplay]:
    """`yfinance.Ticker` replaced by the recorded fixtures."""
    stub = YFReplay()
    stub.install(monkeypatch)
    saved = (yf.config.debug.hide_exceptions, yf.config.network.retries)  # the provider sets these
    yield stub
    yf.config.debug.hide_exceptions, yf.config.network.retries = saved


@pytest.fixture
def clock() -> FakeClock:
    """A Wednesday during LSE trading hours, the day after the fixtures' last bar."""
    return FakeClock(datetime(2026, 11, 25, 10, 0, tzinfo=UTC))


def make_config(symbols: list[str], prices_days: int = 700) -> RunConfig:
    """`runs/m4_prices.yaml` over `symbols`, with lookbacks that fit the 2-year fixtures.

    The shipped config asks for ten years; the fixtures hold two (prices) and one (fx), and a
    longer request would correctly be flagged as truncated history.
    """
    cfg = RunConfig.from_yaml(RUN_YAML)
    return cfg.model_copy(
        update={
            "candidates": [CandidateRef(id=s) for s in symbols],
            "nodes": {"prices": {"lookback_days": prices_days}, "fx": {"lookback_days": 360}},
        }
    )


@pytest.fixture
def run_once(tmp_path: Path, clock: FakeClock) -> Runner:
    """Run the config on the fake clock into `tmp_path` (the same store every call)."""

    async def run(symbols: list[str] = SYMBOLS, *, offline: bool = False, prices_days: int = 700) -> Any:
        cfg = make_config(symbols, prices_days)
        assert cfg.sources is not None
        blobs = FileBlobStore(tmp_path / "blobs")
        store = build_source_store(cfg.sources, tmp_path, blobs, clock=clock, offline=offline)
        try:
            return await arun(cfg, build_registry(), store_root=tmp_path, services={"sources": store})
        finally:
            store.close()

    return run


def open_store(root: Path, clock: FakeClock) -> DuckDBSourceStore:
    """Reopen the run's source store for inspection (close it before the next run)."""
    cfg = make_config(SYMBOLS)
    assert cfg.sources is not None
    return build_source_store(cfg.sources, root, FileBlobStore(root / "blobs"), clock=clock)


def output(result: Any, node: str, candidate: str | None) -> pd.DataFrame:
    """The frame a node produced for a candidate (None for the shared fx node)."""
    return next(v for k, v in result.values.items() if k.name == node and k.candidate == candidate)


def test_registry_and_catalog_expose_the_fetch_nodes() -> None:
    assert sorted(build_registry().names()) == ["fx", "prices", "profile"]
    assert (Prices().lookback_days or 0) >= 3653
    assert Profile.dataset == "profile"
    assert FxRates().entities == ["GBP", "EUR", "CHF", "SEK", "NOK", "DKK", "PLN"]


async def test_second_run_makes_no_yfinance_calls(run_once: Runner, replay: YFReplay) -> None:
    first = await run_once()
    assert first.status == "ok"
    assert all(r.status == "ok" for r in first.results.values())
    assert replay.calls  # run 1 fetched
    replay.calls.clear()
    second = await run_once()
    assert all(r.status == "ok" for r in second.results.values())
    assert replay.calls == []


async def test_offline_rerun_serves_from_the_store(run_once: Runner, replay: YFReplay) -> None:
    await run_once()
    replay.calls.clear()
    result = await run_once(offline=True)
    assert all(r.status == "ok" for r in result.results.values())
    assert replay.calls == []


async def test_gbp_minor_unit_normalised_in_run_output(run_once: Runner, replay: YFReplay) -> None:
    result = await run_once()
    prices = output(result, "prices", "BP.L")
    assert set(prices["currency"]) == {"GBP"}
    last = prices.iloc[-1]
    assert last["close"] == pytest.approx(5.444, rel=1e-3)  # 544.4 GBp from the fixture
    assert all("minor_unit" in repairs for repairs in prices["repairs"].tolist())


async def test_live_bar_never_stored(
    run_once: Runner, replay: YFReplay, clock: FakeClock, tmp_path: Path
) -> None:
    replay.add_bar("BP.L", TODAY, close=999.0)  # Yahoo serving today's still-forming bar
    await run_once(["BP.L"])
    store = open_store(tmp_path, clock)
    try:
        stored = store.query("prices", "BP.L", None).frame
        attempts = store.attempts("prices", "BP.L")
    finally:
        store.close()
    assert pd.Timestamp(TODAY) not in set(stored["date"])
    assert max(stored["date"].tolist()) == pd.Timestamp(LAST_FIXTURE_DAY)
    assert "unsettled" in {a.kind for a in attempts}


async def test_suspect_rows_surface(run_once: Runner, replay: YFReplay, tmp_path: Path) -> None:
    # Constructed, not recorded: one BP.L close multiplied by 100 on a day mid-history.
    bad_day = date(2026, 6, 10)
    replay.scale_close("BP.L", bad_day, 100.0)
    result = await run_once(["BP.L"])
    prices = output(result, "prices", "BP.L")
    row = prices[prices["date"] == pd.Timestamp(bad_day)].iloc[0]
    assert row["quality"] == "suspect"
    assert "jump_x100" in row["quality_reasons"]
    cli = CliRunner().invoke(main, ["sources", "status", "--store", str(tmp_path), "--suspect"])
    assert cli.exit_code == 0, cli.output
    assert "suspect BP.L" in cli.output
    assert "jump_x100" in cli.output


async def test_unknown_ticker_is_empty_not_failure(
    run_once: Runner, replay: YFReplay, clock: FakeClock, tmp_path: Path
) -> None:
    symbols = ["BP.L", "NOSUCH.L"]
    first = await run_once(symbols)
    assert all(r.status == "ok" for r in first.results.values())
    assert len(output(first, "prices", "NOSUCH.L")) == 0
    assert "close" in output(first, "prices", "NOSUCH.L").columns
    store = open_store(tmp_path, clock)
    try:
        assert "empty" in {a.kind for a in store.attempts("prices", "NOSUCH.L")}
    finally:
        store.close()
    replay.calls.clear()
    await run_once(symbols)
    assert [c for c in replay.calls if c.symbol == "NOSUCH.L"] == []


@pytest.mark.parametrize("symbol", ["SAP.DE", "MC.PA"])
async def test_ten_year_history_with_only_its_newest_bar_repaired_is_stored(
    run_once: Runner, replay: YFReplay, symbol: str
) -> None:
    """The live demo failed on these two: ~2500 bars, repaired only on the last one (see fixtures README)."""
    replay.histories[symbol] = YFHistoryPayload.model_validate_json(
        (YF_FIXTURES / f"prices_{symbol}_10y.json").read_text()
    )
    result = await run_once([symbol], prices_days=3653)
    assert all(r.status == "ok" for r in result.results.values()), result.results
    prices = output(result, "prices", symbol)
    assert len(prices) > 2500
    assert set(prices["currency"]) == {"EUR"}
    assert 10 < prices["close"].iloc[-1] < 1000


async def test_fx_rates_cover_all_currencies(run_once: Runner, replay: YFReplay) -> None:
    result = await run_once(["BP.L"])
    fx = output(result, "fx", None)
    assert set(fx["entity"]) == FX_CURRENCIES


def test_shipped_run_config_matches_the_m4_spec() -> None:
    cfg = RunConfig.from_yaml(RUN_YAML)
    assert [c.id for c in cfg.candidates] == [
        "BP.L", "HSBA.L", "VOD.L", "SHEL.L", "ULVR.L", "ASML.AS",
        "SAP.DE", "MC.PA", "NESN.SW", "NOVO-B.CO", "AAPL",
    ]  # fmt: skip
    assert cfg.targets == ["prices", "profile", "fx"]
    assert cfg.registry == "alpha_nodes.registry:build_registry"
    assert cfg.sources is not None
    assert cfg.sources.catalog == "alpha_nodes.catalog:CATALOG"
    assert cfg.sources.providers == {"prices": ["yfinance"], "profile": ["yfinance"], "fx": ["yfinance"]}
