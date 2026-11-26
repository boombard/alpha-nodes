"""The `lensgraph` command line (click): run a YAML run config, (re)build a run's report, inspect the source store.

See documentation/design/core.md, Run configuration (CLI usage) and Reporting: run view.
A report is the prebuilt app plus the run's data (`install_app` + `write_run_view`), written
from the run index and blobs alone, so `lensgraph report` can rebuild it any time later.

Exit codes: 0 ok (failed nodes are data, not errors), 2 config or params error, 3 aborted run.
"""

import asyncio
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import click
import duckdb
import yaml
from pydantic import ValidationError

from .config import RunConfig, Settings, load_object
from .executor.base import RunAborted
from .glossary import Glossary, GlossaryError
from .graph import GraphError
from .plan import RunResult
from .registry import NodeRegistry
from .run import arun
from .sources.coverage import CoverageState
from .store.duckdb_index import DuckDBRunIndex
from .store.files import FileBlobStore
from .view import build_run_view, install_app, write_run_view

EXIT_OK, EXIT_CONFIG, EXIT_ABORTED = 0, 2, 3
DEFAULT_MAX_ROWS = 200
MAX_FAILED_LINES = 20
_STATUS_ORDER = ("ok", "recovered", "failed", "skipped")


class CliError(click.ClickException):
    """A user-facing failure (bad config, params or run id): one line on stderr, exit code 2."""

    exit_code = EXIT_CONFIG


_STORE = click.option(
    "--store",
    type=click.Path(path_type=Path),
    help="Store root (default: LENSGRAPH_STORE_ROOT, else .lensgraph).",
)


@click.group()
def main() -> None:
    """Run lens panels from YAML run configs and build their reports."""


@main.command("run")
@click.argument("config", type=click.Path(path_type=Path))
@_STORE
@click.option("--invalidate", "invalidate", multiple=True, metavar="NODE", help="Also invalidate NODE (repeatable).")
@click.option("--no-cache", is_flag=True, help="Ignore every cached output.")
@click.option("--profile", help="Force this model profile on every AI node.")
@click.option("--no-report", is_flag=True, help="Skip writing the report.")
@click.option("--offline", is_flag=True, help="Never call a provider: serve the sources from the store only.")
@click.option(
    "--path", "paths", multiple=True, type=click.Path(path_type=Path), metavar="DIR",
    help="Prepend DIR to sys.path before importing the registry/services refs (repeatable).",
)
def run_command(
    config: Path,
    store: Path | None,
    invalidate: tuple[str, ...],
    no_cache: bool,
    profile: str | None,
    no_report: bool,
    offline: bool,
    paths: tuple[Path, ...],
) -> None:
    """Run the YAML run config CONFIG and write its report."""
    cfg = _load_config(config, invalidate, no_cache, profile, offline)
    registry, services = _load_wiring(cfg, paths)
    root = _store_root(store)
    code = EXIT_OK
    try:
        result = asyncio.run(arun(cfg, registry, store_root=root, services=services))
    except RunAborted as exc:
        click.echo(f"Error: {exc}", err=True)
        result, code = exc.result, EXIT_ABORTED
    except GraphError as exc:
        raise CliError(str(exc)) from exc
    run_id = result.run_id
    click.echo(f"run id: {run_id}")
    click.echo(f"store: {root}")
    for line in _node_status_lines(result):
        click.echo(line)
    if cfg.report.enabled and not no_report:
        out_dir = cfg.report.out_dir or root / "reports" / run_id
        click.echo(f"report: {_write_report(root, run_id, out_dir, cfg.report.max_rows)}")
    sys.exit(code)


def _node_status_lines(result: RunResult) -> list[str]:
    """The `nodes:` counts line plus one `failed:` line per failed node (see core.md, CLI).

    Zero counts are omitted. Failed lines show the node key, `name[candidate]`, and the first line
    of its error, capped at `MAX_FAILED_LINES` with an `… and N more` tail. Skipped nodes are only
    counted.
    """
    counts = Counter(r.status for r in result.results.values())
    lines = []
    if counts:
        lines.append("nodes: " + ", ".join(f"{counts[s]} {s}" for s in _STATUS_ORDER if counts[s]))
    failed = [r for r in result.results.values() if r.status == "failed"]
    for r in failed[:MAX_FAILED_LINES]:
        message = (r.error or "").strip()
        lines.append(f"failed: {r.key}: {message.splitlines()[0] if message else 'no error recorded'}")
    if len(failed) > MAX_FAILED_LINES:
        lines.append(f"… and {len(failed) - MAX_FAILED_LINES} more")
    return lines


@main.command("report")
@click.argument("run_id")
@_STORE
@click.option("--out", type=click.Path(path_type=Path), help="Report directory (default: <store>/reports/<run_id>).")
def report_command(run_id: str, store: Path | None, out: Path | None) -> None:
    """Rebuild the report of RUN_ID from the index and blobs alone."""
    root = _store_root(store)
    if not (root / "index.duckdb").exists():
        raise CliError(f"no run index in {root}")
    click.echo(f"report: {_write_report(root, run_id, out or root / 'reports' / run_id, None)}")


@main.command("glossary")
@click.argument("directory", type=click.Path(path_type=Path, exists=True, file_okay=False))
def glossary_command(directory: Path) -> None:
    """Validate the glossary in DIRECTORY and list `status  id  fields`, drafts first.

    Exits 1 with the error on stderr when an entry is invalid (core.md, Glossary).
    """
    try:
        glossary = Glossary.load(directory)
    except GlossaryError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    rows = sorted(glossary.entries.values(), key=lambda e: (e.status != "draft", e.id))
    for entry in rows:
        click.echo("  ".join(part for part in (entry.status, entry.id, ", ".join(entry.fields)) if part))


@main.group("sources")
def sources_group() -> None:
    """Inspect the source store."""


@sources_group.command("status")
@_STORE
@click.option("--dataset", help="Only this dataset.")
@click.option("--suspect", is_flag=True, help="List suspect rows (entity, key, reasons).")
def sources_status_command(store: Path | None, dataset: str | None, suspect: bool) -> None:
    """Per dataset and provider: entities, covered ranges, attempts by kind, suspect/rejected rows.

    Reads `<store>/sources.duckdb` only; no catalog is needed. Row counts cover every stored
    version of every fact, not just the latest.
    """
    root = _store_root(store)
    path = root / "sources.duckdb"
    if not path.exists():
        raise CliError(f"no source store in {root}")
    con = duckdb.connect(str(path), read_only=True)
    try:
        if dataset is not None:
            available = sorted(
                r[0].removeprefix("facts_")
                for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'facts\\_%' ESCAPE '\\'").fetchall()
            )
            if dataset not in available:
                raise CliError(f"unknown dataset {dataset!r}; available: {', '.join(available) or 'none'}")
        for line in _status_lines(con, dataset, suspect):
            click.echo(line)
    finally:
        con.close()


def _status_lines(con: duckdb.DuckDBPyConnection, only: str | None, suspect: bool) -> list[str]:
    """The `sources status` report as lines (see `sources_status_command`)."""
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    datasets = sorted(t.removeprefix("facts_") for t in tables if t.startswith("facts_"))
    lines: list[str] = []
    for ds in datasets:
        if only is not None and ds != only:
            continue
        facts = '"facts_' + ds.replace('"', '""') + '"'
        providers = sorted(
            {r[0] for r in con.execute("SELECT provider FROM attempts WHERE dataset=?", [ds]).fetchall()}
            | {r[0] for r in con.execute("SELECT provider FROM coverage WHERE dataset=?", [ds]).fetchall()}
        )
        lines.append(f"dataset {ds}")
        for provider in providers:
            ranges = [
                (entity, CoverageState.model_validate_json(state).settled)
                for entity, state in con.execute(
                    "SELECT entity, state FROM coverage WHERE dataset=? AND provider=? ORDER BY entity",
                    [ds, provider],
                ).fetchall()
            ]
            kinds = con.execute(
                "SELECT kind, count(*) FROM attempts WHERE dataset=? AND provider=? GROUP BY kind ORDER BY kind",
                [ds, provider],
            ).fetchall()
            counts = dict(
                con.execute(
                    f"SELECT quality, count(*) FROM {facts} WHERE provider=? GROUP BY quality", [provider]
                ).fetchall()
            )
            entities = con.execute(
                f"SELECT count(DISTINCT entity) FROM {facts} WHERE provider=?", [provider]
            ).fetchone()
            lines.append(f"  provider {provider}")
            lines.append(f"    entities: {entities[0] if entities else 0}")
            for entity, settled in ranges:
                covered = ", ".join(f"{i.start}..{i.end}" for i in settled.intervals) or "none"
                lines.append(f"    covered {entity}: {covered}")
            lines.append("    attempts: " + (" ".join(f"{k}={n}" for k, n in kinds) or "none"))
            lines.append(f"    rows: suspect={counts.get('suspect', 0)} rejected={counts.get('rejected', 0)}")
            if suspect:
                lines.extend(_suspect_lines(con, facts, provider))
    return lines


def _suspect_lines(con: duckdb.DuckDBPyConnection, facts: str, provider: str) -> list[str]:
    """One line per suspect fact row: entity, its canonical columns (the key), and the reasons."""
    cursor = con.execute(f"SELECT * FROM {facts} WHERE provider=? AND quality='suspect'", [provider])
    names = [d[0] for d in cursor.description]
    canonical = names[: names.index("entity")]  # canonical columns come first, then entity and the meta
    out = []
    for row in sorted(cursor.fetchall(), key=lambda r: (r[names.index("entity")], str(r[:1]))):
        rec = dict(zip(names, row, strict=True))
        key = " ".join(f"{c}={_plain(rec[c])}" for c in canonical)
        out.append(f"    suspect {rec['entity']} {key} reasons={','.join(rec['quality_reasons'])}")
    return out


def _plain(value: Any) -> str:
    """A cell for display: timestamps as their date when at midnight."""
    text = str(value)
    return text.removesuffix(" 00:00:00")


def _store_root(arg: Path | None) -> Path:
    """`--store`, else `LENSGRAPH_STORE_ROOT`, else the `Settings` default."""
    return arg if arg is not None else Settings().store_root


def _load_config(
    path: Path, invalidate: Sequence[str], no_cache: bool, profile: str | None, offline: bool = False
) -> RunConfig:
    """Load the YAML config and apply the command-line overrides; `CliError` on any problem."""
    try:
        config = RunConfig.from_yaml(path)
    except OSError as exc:
        raise CliError(f"cannot read config {path}: {exc.strerror or exc}") from exc
    except yaml.YAMLError as exc:
        raise CliError(f"{path} is not valid YAML: {exc}".replace("\n", " ")) from exc
    except ValidationError as exc:
        raise CliError(_one_line(exc)) from exc
    update: dict[str, Any] = {"invalidate": [*config.invalidate, *invalidate]}
    if no_cache:
        update["no_cache"] = True
    if profile:
        update["profile_override"] = profile
    if offline:
        if config.sources is None:
            raise CliError("--offline needs a `sources:` section in the config")
        update["sources"] = config.sources.model_copy(update={"offline": True})
    return config.model_copy(update=update)


def _one_line(exc: ValidationError) -> str:
    """A validation error as one line naming each offending key."""
    parts = [f"{'.'.join(map(str, e['loc'])) or 'config'}: {e['msg']}" for e in exc.errors()]
    return "invalid config: " + "; ".join(parts)


def _load_wiring(config: RunConfig, paths: Sequence[Path]) -> tuple[NodeRegistry, Any]:
    """Import the registry and services named in the config (after prepending `--path`)."""
    for path in reversed(list(paths)):
        sys.path.insert(0, str(path.resolve()))
    try:
        registry = load_object(config.registry)
        services = load_object(config.services) if config.services else None
    except (ImportError, AttributeError) as exc:
        raise CliError(str(exc)) from exc
    if not isinstance(registry, NodeRegistry):
        raise CliError(f"registry {config.registry!r} is not a NodeRegistry")
    return registry, services


def _write_report(store: Path, run_id: str, out_dir: Path, max_rows: int | None) -> Path:
    """Write the app and the run's data into `out_dir`; returns its `index.html`.

    `max_rows` defaults to the stored run config's `report.max_rows`.
    """
    index = DuckDBRunIndex(store / "index.duckdb")
    try:
        try:
            if max_rows is None:
                stored = index.run_config(run_id).get("report") or {}
                max_rows = int(stored.get("max_rows", DEFAULT_MAX_ROWS))
            view = build_run_view(run_id, index, FileBlobStore(store / "blobs"), max_rows=max_rows)
        except KeyError as exc:
            raise CliError(f"unknown run {run_id!r} in {store}") from exc
    finally:
        index.close()
    page = install_app(out_dir)
    write_run_view(view, out_dir)
    return page


if __name__ == "__main__":
    main()
