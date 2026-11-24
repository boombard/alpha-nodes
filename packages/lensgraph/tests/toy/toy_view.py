"""Helper: run the toy panel with its reviewer and expose the stores a `RunView` is built from."""

from pathlib import Path

import duckdb
from lensgraph import AssessmentBrief, Panel, RunSpec, run
from lensgraph.panel import panel_registry
from lensgraph.store.duckdb_index import DuckDBRunIndex
from lensgraph.store.files import FileBlobStore
from lensgraph.types import CandidateRef
from pydantic import BaseModel, ConfigDict

from .registry import build_registry, build_services

TOY_RUN_ID = "toy-run"
FIXED_START = "2026-01-01 00:00:00"
FIXED_FINISH = "2026-01-01 00:00:05"
BRIEF = AssessmentBrief(purpose="Pick strains for a pilot", priorities=["speed", "safety"])
PANEL = Panel(lenses=["growth_lens", "safety_lens"], reviewer="toy_reviewer")


class ToyRun(BaseModel):
    """Where a finished toy run lives, with opened-on-demand stores."""

    model_config = ConfigDict(frozen=True)
    root: Path
    run_id: str = TOY_RUN_ID

    def index(self) -> DuckDBRunIndex:
        """A fresh index handle; the caller closes it."""
        return DuckDBRunIndex(self.root / "index.duckdb")

    def blobs(self) -> FileBlobStore:
        """The run's blob store."""
        return FileBlobStore(self.root / "blobs")


def run_toy_panel(root: Path) -> ToyRun:
    """Run the three-strain toy panel (growth + safety lenses, reviewer) into `root`, with fixed run id and times."""
    spec = RunSpec(
        panel=PANEL,
        candidates=[CandidateRef(id=s) for s in ("S1", "S2", "S3")],
        targets=PANEL.targets(),
        nodes={
            "safety_lens": {"profile": "test"},
            "review": {"profile": "test", "brief": BRIEF.model_dump()},
        },
    )
    run(
        spec,
        panel_registry(PANEL, build_registry()),
        store_root=root,
        services=build_services(),
        run_id=TOY_RUN_ID,
    )
    _fix_run_times(root / "index.duckdb")
    return ToyRun(root=root)


def _fix_run_times(index_path: Path) -> None:
    """Pin the run's start/finish times (volatile wall-clock values) so views are comparable.

    The library never normalises them; only this test helper rewrites the index row, so
    cross-run determinism and the committed UI fixture stay meaningful.
    """
    con = duckdb.connect(str(index_path))
    try:
        con.execute(
            "UPDATE runs SET started_at = ?::TIMESTAMP, finished_at = ?::TIMESTAMP",
            [FIXED_START, FIXED_FINISH],
        )
    finally:
        con.close()
