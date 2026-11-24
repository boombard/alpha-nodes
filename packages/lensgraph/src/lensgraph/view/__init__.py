"""Run view: the `RunView` data contract and its export; see documentation/design/core.md,
Reporting: run view (one app, one contract).
"""

import shutil
from pathlib import Path

from .build import build_run_view, render_run_json, write_run_view
from .models import (
    CandidateView,
    CitedView,
    ClaimRef,
    FlagRef,
    RunSummary,
    RunView,
    TableData,
)
from .schema import run_view_schema, schema_hash

APP_BUNDLE = Path(__file__).parent / "app" / "index.html"


def install_app(out_dir: Path) -> Path:
    """Copy the prebuilt single-file run view app into `out_dir`; returns the new `index.html`.

    The app opens from file:// and reads `data/run.js` (or `run.json`) next to it; see
    `write_run_view`. The bundle is built from `packages/lensgraph-ui` and committed, so Python
    users never need Node (documentation/design/core.md, Reporting: run view).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copyfile(APP_BUNDLE, out_dir / "index.html"))


__all__ = [
    "CandidateView",
    "CitedView",
    "ClaimRef",
    "FlagRef",
    "RunSummary",
    "RunView",
    "TableData",
    "build_run_view",
    "install_app",
    "render_run_json",
    "run_view_schema",
    "schema_hash",
    "write_run_view",
]
