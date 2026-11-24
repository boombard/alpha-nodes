"""The `lensgraph` command line (click): run a YAML run config, and (re)build a run's report.

See documentation/design/core.md, Run configuration (CLI usage) and Reporting: run view.
A report is the prebuilt app plus the run's data (`install_app` + `write_run_view`), written
from the run index and blobs alone, so `lensgraph report` can rebuild it any time later.

Exit codes: 0 ok (failed nodes are data, not errors), 2 config or params error, 3 aborted run.
"""

import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import click
import yaml
from pydantic import ValidationError

from .config import RunConfig, Settings, load_object
from .executor.base import RunAborted
from .graph import GraphError
from .registry import NodeRegistry
from .run import arun
from .store.duckdb_index import DuckDBRunIndex
from .store.files import FileBlobStore
from .view import build_run_view, install_app, write_run_view

EXIT_OK, EXIT_CONFIG, EXIT_ABORTED = 0, 2, 3
DEFAULT_MAX_ROWS = 200


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
    paths: tuple[Path, ...],
) -> None:
    """Run the YAML run config CONFIG and write its report."""
    cfg = _load_config(config, invalidate, no_cache, profile)
    registry, services = _load_wiring(cfg, paths)
    root = _store_root(store)
    code = EXIT_OK
    try:
        run_id = asyncio.run(arun(cfg, registry, store_root=root, services=services)).run_id
    except RunAborted as exc:
        click.echo(f"Error: {exc}", err=True)
        run_id, code = exc.result.run_id, EXIT_ABORTED
    except GraphError as exc:
        raise CliError(str(exc)) from exc
    click.echo(f"run id: {run_id}")
    click.echo(f"store: {root}")
    if cfg.report.enabled and not no_report:
        out_dir = cfg.report.out_dir or root / "reports" / run_id
        click.echo(f"report: {_write_report(root, run_id, out_dir, cfg.report.max_rows)}")
    sys.exit(code)


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


def _store_root(arg: Path | None) -> Path:
    """`--store`, else `LENSGRAPH_STORE_ROOT`, else the `Settings` default."""
    return arg if arg is not None else Settings().store_root


def _load_config(
    path: Path, invalidate: Sequence[str], no_cache: bool, profile: str | None
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
