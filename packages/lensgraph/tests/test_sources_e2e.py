"""A run config with a `sources:` section, end to end on the toy domain."""

from pathlib import Path

import pytest
from lensgraph import RunConfig, arun
from lensgraph.graph import ParamsError
from toy import sources_nodes
from toy.sources_nodes import build_registry

TOY_SOURCES_YAML = Path(__file__).parent / "toy" / "sources_run.yaml"


@pytest.fixture(autouse=True)
def _fresh_providers() -> None:
    sources_nodes.CREATED.clear()


def config(**sources: object) -> RunConfig:
    cfg = RunConfig.from_yaml(TOY_SOURCES_YAML)
    assert cfg.sources is not None
    return cfg.model_copy(update={"sources": cfg.sources.model_copy(update=sources)})


async def test_two_runs_fetch_only_once(tmp_path: Path) -> None:
    cfg = RunConfig.from_yaml(TOY_SOURCES_YAML)
    first = await arun(cfg, build_registry(), store_root=tmp_path)
    assert all(r.status == "ok" for r in first.results.values())
    assert sources_nodes.CREATED["fake"].calls  # type: ignore[attr-defined]  # run 1 fetched
    second = await arun(cfg, build_registry(), store_root=tmp_path)
    assert all(r.status == "ok" for r in second.results.values())
    assert sources_nodes.CREATED["fake"].calls == []  # type: ignore[attr-defined]  # run 2: a new provider, never called
    assert (tmp_path / "sources.duckdb").exists()


async def test_offline_rerun_serves_from_store(tmp_path: Path) -> None:
    await arun(RunConfig.from_yaml(TOY_SOURCES_YAML), build_registry(), store_root=tmp_path)
    sources_nodes.CREATED.clear()
    result = await arun(config(offline=True), build_registry(), store_root=tmp_path)
    assert all(r.status == "ok" for r in result.results.values())
    provider = sources_nodes.CREATED.get("fake")
    assert provider is None or provider.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("providers", "named"),
    [
        ({"assays": ["nope"], "strain_info": ["fake"]}, "nope"),
        ({"assays": ["fake"], "bogus": ["fake"]}, "bogus"),
    ],
)
async def test_unknown_provider_name_is_params_error(
    tmp_path: Path, providers: dict[str, list[str]], named: str
) -> None:
    with pytest.raises(ParamsError, match=named):
        await arun(config(providers=providers), build_registry(), store_root=tmp_path)


async def test_index_failure_does_not_leak_the_source_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    import duckdb

    run_module = importlib.import_module("lensgraph.run")  # `lensgraph.run` the attribute is the function
    built: list[object] = []
    real_build = run_module.build_source_store

    def spy(*args: object, **kwargs: object) -> object:
        built.append(real_build(*args, **kwargs))
        return built[-1]

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(run_module, "build_source_store", spy)
    monkeypatch.setattr(run_module, "DuckDBRunIndex", boom)
    with pytest.raises(RuntimeError, match="index unavailable"):
        await arun(RunConfig.from_yaml(TOY_SOURCES_YAML), build_registry(), store_root=tmp_path)
    (store,) = built
    with pytest.raises(duckdb.ConnectionException):  # the store's connection was closed
        store.attempts()  # type: ignore[attr-defined]
    duckdb.connect(str(tmp_path / "sources.duckdb")).close()  # and the file can be reopened
