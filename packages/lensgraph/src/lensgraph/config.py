"""Run configuration: environment settings and the YAML-loadable `RunConfig`.

See documentation/design/core.md, Run configuration.
"""

import importlib
import inspect
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

from .run import RunSpec
from .verdict import AssessmentBrief


class Settings(BaseSettings):
    """Process-wide settings read from `LENSGRAPH_*` environment variables.

    Args:
        store_root: where blobs, the run index and reports live.
        local_model: model string for the `local` LLM profile (`LENSGRAPH_LOCAL_MODEL`).
    """

    model_config = SettingsConfigDict(env_prefix="LENSGRAPH_", extra="ignore")
    store_root: Path = Path(".lensgraph")
    local_model: str | None = None


class ReportOptions(BaseModel):
    """How the end-of-run report is written.

    Args:
        enabled: write a report at all.
        out_dir: report directory; defaults to `<store_root>/reports/<run_id>`.
        max_rows: cap on rows per table in the report.
    """

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    out_dir: Path | None = None
    max_rows: int = 200


class RunConfig(RunSpec):
    """A `RunSpec` plus the wiring needed to run it from a file: registry, services, brief, report.

    Args:
        registry: "module:attr" of a `NodeRegistry` or a zero-arg factory returning one.
        services: "module:attr" of a mapping or a zero-arg factory returning one.
    """

    registry: str
    services: str | None = None
    brief: AssessmentBrief | None = None
    report: ReportOptions = ReportOptions()

    @classmethod
    def from_yaml(cls, path: Path) -> "RunConfig":
        """Load a config from YAML; unknown keys raise a `ValidationError` naming them."""
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))


def load_object(ref: str) -> Any:
    """Import "pkg.mod:attr" and return it, calling it first if it is a zero-arg non-class callable.

    Raises `ImportError` or `AttributeError`, naming `ref`, for a bad module or attribute.
    """
    module_name, _, attr = ref.partition(":")
    if not module_name or not attr:
        raise ImportError(f"bad object reference {ref!r}; expected 'pkg.mod:attr'")
    try:
        obj: Any = importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(f"cannot import {ref!r}: {exc}") from exc
    for part in attr.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError as exc:
            raise AttributeError(f"cannot resolve {ref!r}: {exc}") from exc
    if callable(obj) and not inspect.isclass(obj) and _takes_no_args(obj):
        return obj()
    return obj


def _takes_no_args(fn: Any) -> bool:
    """True if `fn` can be called with no arguments."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return all(p.default is not p.empty or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params)
