"""Run API: turn a `RunSpec` into a plan and execute it on disk-backed stores.

This is the public entry point of the core; see documentation/design/core.md, Run
configuration and Memoization (last bullet: the escape hatches).
"""

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .executor.asyncio_executor import AsyncioExecutor
from .executor.base import Executor, RunAborted
from .executor.limits import ResourceLimit
from .graph import ParamsError, build_plan
from .panel import Panel, panel_registry
from .plan import RunResult
from .registry import NodeRegistry
from .store.duckdb_index import DuckDBRunIndex
from .store.files import FileBlobStore
from .types import CandidateRef


class RunSpec(BaseModel):
    """Everything that configures one run; stored verbatim in the run index.

    Args:
        targets: node names to compute (their dependencies are pulled in).
        panel: if set and `targets` is empty, the run targets the panel's aggregator.
        candidates: the candidates to expand per-candidate nodes over.
        nodes: per-node parameter overrides, keyed by node name.
        limits: per-resource concurrency/rate limits (used when no executor is passed).
        invalidate: node names whose cached outputs, and their descendants', are ignored.
        no_cache: ignore every cached output (results are still saved for later runs).
    """

    model_config = ConfigDict(extra="forbid")
    targets: list[str] = []
    panel: Panel | None = None
    candidates: list[CandidateRef]
    nodes: dict[str, dict[str, Any]] = {}
    limits: dict[str, ResourceLimit] = {}
    invalidate: list[str] = []
    no_cache: bool = False


async def arun(
    spec: RunSpec,
    registry: NodeRegistry,
    *,
    store_root: Path,
    services: Mapping[str, Any] | None = None,
    executor: Executor | None = None,
    run_id: str | None = None,
) -> RunResult:
    """Plan and execute `spec`, recording the run in `store_root/index.duckdb`.

    Blobs live in `store_root/blobs`. Raises `ParamsError` if `spec.invalidate` names a node
    not in the plan; any other failure after the run starts marks it "failed" in the index. `RunAborted` (a `GlobalFailure` in a node) propagates;
    the aborted run is still recorded, and cached results let the next run resume.
    """
    store_root = Path(store_root)
    store_root.mkdir(parents=True, exist_ok=True)
    if not spec.targets and spec.panel is None:
        raise ParamsError("RunSpec needs targets or a panel")
    if spec.panel is not None and spec.panel.aggregator not in registry.names():
        registry = panel_registry(spec.panel, registry)
    targets = spec.targets or ([spec.panel.aggregator] if spec.panel else [])
    plan = build_plan(
        targets, registry, spec.candidates, node_params=spec.nodes, run_id=run_id
    )
    unknown = sorted({n for n in spec.invalidate if not any(k.name == n for k in plan.nodes)})
    if unknown:
        raise ParamsError(f"invalidate names not in the plan: {unknown}")
    bypass = set(plan.nodes) if spec.no_cache else plan.descendants(set(spec.invalidate))
    blobs = FileBlobStore(store_root / "blobs")
    index = DuckDBRunIndex(store_root / "index.duckdb")
    try:
        index.start_run(plan.run_id, spec.model_dump(mode="json"))
        runner = executor or AsyncioExecutor(limits=spec.limits)
        result = await runner.execute(plan, blobs, index, services=services, bypass_memo=bypass)
        index.finish_run(plan.run_id, "ok")
        return result
    except RunAborted:
        raise  # the executor already recorded "aborted"
    except BaseException:  # includes cancellation / KeyboardInterrupt: never leave "running"
        index.finish_run(plan.run_id, "failed")
        raise
    finally:
        index.close()


def run(spec: RunSpec, registry: NodeRegistry, **kwargs: Any) -> RunResult:
    """Synchronous wrapper around `arun` (`asyncio.run`); takes the same keyword arguments."""
    return asyncio.run(arun(spec, registry, **kwargs))
