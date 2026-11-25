"""The `lensgraph` CLI, driven in-process against the toy domain with tmp_path stores."""

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from lensgraph.cli import main
from lensgraph.config import RunConfig
from lensgraph.llm import ProfileRegistry
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.view import RunView
from toy.sources import FakeAssaySource

TESTS_DIR = Path(__file__).parent
TOY_YAML = TESTS_DIR / "toy" / "toy_run.yaml"
AI_NODES = {"safety_lens", "review"}


def _cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, str], str]:
    """Run `main(argv)`; return (exit code, stdout `key: value` lines as a dict, stderr)."""
    result = CliRunner().invoke(main, list(argv))
    code, out, err = result.exit_code, result.stdout, result.stderr
    fields = dict(line.split(": ", 1) for line in out.splitlines() if ": " in line)
    return code, fields, err


def _run(capsys, store: Path, *extra: str, config: Path = TOY_YAML):
    return _cli(capsys, "run", str(config), "--path", str(TESTS_DIR), "--store", str(store), *extra)


def _results(store: Path, run_id: str):
    index = DuckDBRunIndex(store / "index.duckdb")
    try:
        return {r.key: r for r in index.node_results(run_id)}
    finally:
        index.close()


def _hits(results, names: set[str]) -> set[bool]:
    return {r.cache_hit for k, r in results.items() if k.name in names and r.status == "ok"}


def test_cli_run_toy_writes_report(tmp_path, capsys):
    code, out, _ = _run(capsys, tmp_path)
    assert code == 0
    report = Path(out["report"])
    assert report == tmp_path / "reports" / out["run id"] / "index.html"
    assert out["store"] == str(tmp_path)
    for name in ("index.html", "run.json", "data/run.js"):
        assert (report.parent / name).is_file()
    view = RunView.model_validate_json((report.parent / "run.json").read_text())
    assert view.summary.run_id == out["run id"]
    assert [c.id for c in view.candidates] == ["S1", "S2", "S3"]
    assert all(c.record.review is not None for c in view.candidates)  # brief reached the review


def test_cli_rerun_all_cache_hits(tmp_path, capsys):
    _run(capsys, tmp_path)
    _, out, _ = _run(capsys, tmp_path)
    results = _results(tmp_path, out["run id"])
    memoizable = [r for r in results.values() if r.status == "ok" and r.memo_key is not None]
    assert memoizable
    assert all(r.cache_hit for r in memoizable)


def test_cli_invalidate_and_no_cache(tmp_path, capsys):
    _run(capsys, tmp_path)
    _, out, _ = _run(capsys, tmp_path, "--invalidate", "assay_clean")
    results = _results(tmp_path, out["run id"])
    assert _hits(results, {"assay_clean", "growth_rate"}) == {False}

    _, out, _ = _run(capsys, tmp_path, "--no-cache")
    assert not any(r.cache_hit for r in _results(tmp_path, out["run id"]).values())


def test_cli_profile_override_applies_to_ai_nodes(tmp_path, capsys):
    _run(capsys, tmp_path)
    code, out, _ = _run(capsys, tmp_path, "--profile", "test2")
    assert code == 0
    results = _results(tmp_path, out["run id"])
    assert _hits(results, AI_NODES) == {False}
    assert _hits(results, {"assay_clean", "growth_rate"}) == {True}
    index = DuckDBRunIndex(tmp_path / "index.duckdb")
    try:
        nodes = index.run_config(out["run id"])["nodes"]
    finally:
        index.close()
    assert nodes["safety_lens"]["profile"] == nodes["review"]["profile"] == "test2"


def test_cli_brief_change_reruns_only_review(tmp_path, capsys):
    _run(capsys, tmp_path)
    raw = yaml.safe_load(TOY_YAML.read_text())
    raw["brief"]["horizon"] = "12 months"
    changed = tmp_path / "changed.yaml"
    changed.write_text(yaml.safe_dump(raw))
    _, out, _ = _run(capsys, tmp_path, config=changed)
    results = _results(tmp_path, out["run id"])
    assert _hits(results, {"review"}) == {False}
    assert _hits(results, {"safety_lens", "dossier", "growth_lens"}) == {True}


def test_cli_conflicting_node_brief_exit_2(tmp_path, capsys):
    raw = yaml.safe_load(TOY_YAML.read_text())
    raw["nodes"]["review"]["brief"] = {"purpose": "something else"}
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(raw))
    code, _, err = _run(capsys, tmp_path / "store", config=bad)
    assert code == 2
    assert "brief" in err and "Traceback" not in err


def test_cli_config_error_exit_2(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text(TOY_YAML.read_text() + "\nbogus_key: 1\n")
    code, _, err = _run(capsys, tmp_path / "store", config=bad)
    assert code == 2
    assert "bogus_key" in err
    assert "Traceback" not in err
    assert len(err.strip().splitlines()) == 1


def test_cli_unknown_invalidate_exit_2(tmp_path, capsys):
    code, _, err = _run(capsys, tmp_path, "--invalidate", "nope")
    assert code == 2
    assert "nope" in err


def test_cli_missing_config_exit_2(tmp_path, capsys):
    code, _, err = _cli(capsys, "run", str(tmp_path / "missing.yaml"))
    assert code == 2
    assert "missing.yaml" in err


def test_cli_no_report(tmp_path, capsys):
    code, out, _ = _run(capsys, tmp_path, "--no-report")
    assert code == 0
    assert "report" not in out
    assert not (tmp_path / "reports").exists()


def test_cli_report_out_dir_from_config(tmp_path, capsys):
    raw = yaml.safe_load(TOY_YAML.read_text())
    raw["report"] = {"out_dir": str(tmp_path / "custom")}
    cfg = tmp_path / "custom.yaml"
    cfg.write_text(yaml.safe_dump(raw))
    _, out, _ = _run(capsys, tmp_path / "store", config=cfg)
    assert Path(out["report"]) == tmp_path / "custom" / "index.html"
    assert (tmp_path / "custom" / "run.json").is_file()


def test_cli_store_from_environment(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("LENSGRAPH_STORE_ROOT", str(tmp_path / "env-store"))
    code, out, _ = _cli(capsys, "run", str(TOY_YAML), "--path", str(TESTS_DIR))
    assert code == 0
    assert out["store"] == str(tmp_path / "env-store")


def test_cli_aborted_run_exit_3_and_report(tmp_path, capsys, monkeypatch):
    from lensgraph.types import GlobalFailure

    def boom(self, strain: str):
        raise GlobalFailure("source down")

    monkeypatch.setattr(FakeAssaySource, "assays", boom)
    code, out, err = _run(capsys, tmp_path)
    assert code == 3
    assert "aborted" in err
    assert (Path(out["report"]).parent / "run.json").is_file()


def test_cli_report_rebuilds(tmp_path, capsys):
    _, out, _ = _run(capsys, tmp_path)
    original = Path(out["report"]).parent
    rebuilt = tmp_path / "rebuilt"
    code, rout, _ = _cli(
        capsys, "report", out["run id"], "--store", str(tmp_path), "--out", str(rebuilt)
    )
    assert code == 0
    assert Path(rout["report"]) == rebuilt / "index.html"
    assert (rebuilt / "index.html").is_file() and (rebuilt / "data" / "run.js").is_file()
    assert (rebuilt / "run.json").read_text() == (original / "run.json").read_text()


def test_cli_report_default_out_and_unknown_run(tmp_path, capsys):
    _, out, _ = _run(capsys, tmp_path, "--no-report")
    code, rout, _ = _cli(capsys, "report", out["run id"], "--store", str(tmp_path))
    assert code == 0
    assert Path(rout["report"]) == tmp_path / "reports" / out["run id"] / "index.html"
    code, _, err = _cli(capsys, "report", "no-such-run", "--store", str(tmp_path))
    assert code == 2
    assert "no-such-run" in err


def test_local_model_via_settings(monkeypatch):
    registry = ProfileRegistry()
    monkeypatch.delenv("LENSGRAPH_LOCAL_MODEL", raising=False)
    with pytest.raises(ValueError, match="LENSGRAPH_LOCAL_MODEL"):
        registry.get("local")
    monkeypatch.setenv("LENSGRAPH_LOCAL_MODEL", "ollama:qwen3:8b")
    assert registry.get("local").model == "ollama:qwen3:8b"


def test_run_config_roundtrip_is_stored(tmp_path, capsys):
    """The stored run config is the resolved RunConfig dump (registry refs and brief included)."""
    _, out, _ = _run(capsys, tmp_path)
    index = DuckDBRunIndex(tmp_path / "index.duckdb")
    try:
        stored = index.run_config(out["run id"])
    finally:
        index.close()
    assert stored["registry"] == "toy.registry:build_registry"
    assert stored["nodes"]["review"]["brief"]["horizon"] == "6 months"
    RunConfig.model_validate({**stored, "report": stored["report"]})


SOURCES_YAML = TESTS_DIR / "toy" / "sources_run.yaml"


def test_cli_offline_flag(tmp_path, capsys):
    """A sources run fetches online; `--offline` then serves it from the store, and a gap fails the node."""
    from toy import sources_nodes

    sources_nodes.CREATED.clear()
    code, out, _ = _run(capsys, tmp_path, config=SOURCES_YAML)
    assert code == 0
    assert Path(out["report"]).is_file()  # targets without a panel still build a report
    assert sources_nodes.CREATED["fake"].calls  # type: ignore[attr-defined]

    sources_nodes.CREATED.clear()
    code, out, _ = _run(capsys, tmp_path, "--offline", config=SOURCES_YAML)
    assert code == 0
    assert all(r.status == "ok" for r in _results(tmp_path, out["run id"]).values())
    assert sources_nodes.CREATED["fake"].calls == []  # type: ignore[attr-defined]

    cfg = yaml.safe_load(SOURCES_YAML.read_text())
    cfg["candidates"] = [{"id": "NEW"}]  # never fetched: a gap
    gap = tmp_path / "gap.yaml"
    gap.write_text(yaml.safe_dump(cfg))
    code, out, _ = _run(capsys, tmp_path, "--offline", "--no-report", config=gap)
    assert code == 0
    statuses = {r.status for r in _results(tmp_path, out["run id"]).values()}
    assert "failed" in statuses
    assert sources_nodes.CREATED["fake"].calls == []  # type: ignore[attr-defined]


def _seeded_sources(root: Path) -> None:
    """A source store with one ok, one suspect-row and one failed entity, written straight to `root`."""
    import asyncio
    from datetime import UTC, date, datetime

    from lensgraph.sources import DateInterval, DuckDBSourceStore, FakeClock, SourceUnavailable
    from lensgraph.store.memory import InMemoryBlobStore
    from toy.sources_catalog import ASSAYS, FakeAssayProvider

    provider = FakeAssayProvider()
    provider.spike_days = {date(2026, 3, 3)}
    provider.script = {"BAD": ["error", "error", "error"]}
    store = DuckDBSourceStore(
        root / "sources.duckdb", InMemoryBlobStore(), {"assays": ASSAYS}, {"assays": [provider]},
        clock=FakeClock(datetime(2026, 3, 10, 12, tzinfo=UTC)),
    )
    window = DateInterval(start=date(2026, 3, 1), end=date(2026, 3, 5))
    try:
        asyncio.run(store.get("assays", "S1", window))
        try:
            asyncio.run(store.get("assays", "BAD", window))
        except SourceUnavailable:
            pass
    finally:
        store.close()


def test_cli_sources_status_lists_attempts_and_suspect(tmp_path, capsys):
    _seeded_sources(tmp_path)
    result = CliRunner().invoke(main, ["sources", "status", "--store", str(tmp_path)])
    assert result.exit_code == 0
    out = result.stdout
    assert "assays" in out and "fake" in out
    assert "2026-03-01..2026-03-05" in out  # S1's covered range
    assert "ok=1" in out and "error=" in out  # attempts by kind
    assert "suspect=1" in out and "rejected=0" in out

    result = CliRunner().invoke(main, ["sources", "status", "--store", str(tmp_path), "--suspect"])
    assert result.exit_code == 0
    assert "S1" in result.stdout and "jump_x100" in result.stdout and "2026-03-03" in result.stdout

    other = CliRunner().invoke(main, ["sources", "status", "--store", str(tmp_path), "--dataset", "nope"])
    assert other.exit_code == 2
    assert "nope" in other.stderr and "available: assays" in other.stderr
    one = CliRunner().invoke(main, ["sources", "status", "--store", str(tmp_path), "--dataset", "assays"])
    assert one.exit_code == 0 and "provider fake" in one.stdout


def test_cli_sources_status_without_store_is_config_error(tmp_path):
    result = CliRunner().invoke(main, ["sources", "status", "--store", str(tmp_path)])
    assert result.exit_code == 2
