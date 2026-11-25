"""Run API: turn a `RunSpec` into a plan and execute it on disk-backed stores.

This is the public entry point of the core; see documentation/design/core.md, Run
configuration and Memoization (last bullet: the escape hatches).
"""

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from .ai import AINode
from .cost import llm_calls_from_result
from .executor.asyncio_executor import AsyncioExecutor
from .executor.base import Executor, RunAborted
from .executor.limits import ResourceLimit
from .graph import ParamsError, build_plan, resolve_classes
from .panel import Panel, panel_registry
from .plan import RunResult
from .registry import NodeRegistry
from .review import DossierReviewer
from .sources.catalog import build_source_store
from .store.duckdb_index import DuckDBRunIndex
from .store.files import FileBlobStore
from .types import CandidateRef
from .verdict import AssessmentBrief


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
        profile_override: model profile name forced onto every AI node in the plan (`AINode`
            subclasses and `DossierReviewer`), replacing any `profile` the config sets; the
            CLI's `--profile`.
    """

    model_config = ConfigDict(extra="forbid")
    targets: list[str] = []
    panel: Panel | None = None
    candidates: list[CandidateRef]
    nodes: dict[str, dict[str, Any]] = {}
    limits: dict[str, ResourceLimit] = {}
    invalidate: list[str] = []
    no_cache: bool = False
    profile_override: str | None = None


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

    Blobs live in `store_root/blobs`. `spec` may be a `RunConfig`:
    - its `sources` section builds the source store (`<store_root>/sources.duckdb`), injected as the
      `sources` service unless `services` already has one (which wins) and closed when the run ends;
    - its `brief` is wired into the reviewer's `brief` param;
    - its resolved dump (with that wiring and `profile_override` applied to `nodes`) is stored as the
      run config, which is what `lensgraph report` rebuilds from.
    Targets default to `spec.panel.targets()` (the aggregator, plus the review when set).

    Raises `ParamsError` if `spec.invalidate` names a node not in the plan, or if `brief`
    conflicts with an explicit `nodes.review.brief`; any other failure after the run starts marks
    it "failed" in the index. `RunAborted` (a `GlobalFailure` in a node) propagates; the aborted
    run is still recorded, and cached results let the next run resume.
    """
    store_root = Path(store_root)
    store_root.mkdir(parents=True, exist_ok=True)
    if not spec.targets and spec.panel is None:
        raise ParamsError("RunSpec needs targets or a panel")
    if spec.panel is not None and spec.panel.aggregator not in registry.names():
        registry = panel_registry(spec.panel, registry)
    targets = spec.targets or (spec.panel.targets() if spec.panel else [])
    node_params = _resolve_node_params(spec, targets, registry)
    plan = build_plan(targets, registry, spec.candidates, node_params=node_params, run_id=run_id)
    unknown = sorted({n for n in spec.invalidate if not any(k.name == n for k in plan.nodes)})
    if unknown:
        raise ParamsError(f"invalidate names not in the plan: {unknown}")
    bypass = set(plan.nodes) if spec.no_cache else plan.descendants(set(spec.invalidate))
    blobs = FileBlobStore(store_root / "blobs")
    sources_cfg = getattr(spec, "sources", None)  # only a RunConfig has one (config.py imports this module)
    source_store = None
    try:
        if sources_cfg is not None and "sources" not in (services or {}):
            source_store = build_source_store(sources_cfg, store_root, blobs)
            services = {**(services or {}), "sources": source_store}
        index = DuckDBRunIndex(store_root / "index.duckdb")
    except BaseException:  # the store holds a file lock: never leak it
        if source_store is not None:
            source_store.close()
        raise
    try:
        index.start_run(plan.run_id, {**spec.model_dump(mode="json"), "nodes": node_params})
        index.record_plan(plan.run_id, plan)
        runner = executor or AsyncioExecutor(limits=spec.limits)
        result = await runner.execute(plan, blobs, index, services=services, bypass_memo=bypass)
        _record_llm_calls(index, result)
        index.finish_run(plan.run_id, "ok")
        return result
    except RunAborted as exc:
        _record_llm_calls(index, exc.result)  # the executor already recorded "aborted"
        raise
    except BaseException:  # includes cancellation / KeyboardInterrupt: never leave "running"
        index.finish_run(plan.run_id, "failed")
        raise
    finally:
        index.close()
        if source_store is not None:
            source_store.close()


def _resolve_node_params(
    spec: RunSpec, targets: list[str], registry: NodeRegistry
) -> dict[str, dict[str, Any]]:
    """`spec.nodes` plus the run-level wiring: the brief for the reviewer, the profile override.

    The brief (only a `RunConfig` has one; read with `getattr` because `config.py` imports this
    module) goes to the reviewer as the `brief` node param, so it is part of the memo key. An
    explicit `nodes.<review>.brief` that differs raises `ParamsError`. `profile_override` replaces
    the `profile` param of every AI node in the plan (flags beat the config).
    """
    params = {name: dict(p) for name, p in spec.nodes.items()}
    classes = resolve_classes(targets, registry)
    brief = getattr(spec, "brief", None)
    if isinstance(brief, AssessmentBrief):
        for name, cls in classes.items():
            if not issubclass(cls, DossierReviewer):
                continue
            node = params.setdefault(name, {})
            wanted = brief.model_dump(mode="json")
            if "brief" in node and _as_brief(node["brief"], name) != brief:
                raise ParamsError(
                    f"brief conflicts with nodes.{name}.brief; set it in one place only"
                )
            node["brief"] = wanted
    if spec.profile_override:
        for name, cls in classes.items():
            if issubclass(cls, AINode | DossierReviewer):
                params.setdefault(name, {})["profile"] = spec.profile_override
    return params


def _as_brief(value: Any, node: str) -> AssessmentBrief:
    """Validate an explicit `brief` param of `node`; `ParamsError` if it is not a brief."""
    try:
        return AssessmentBrief.model_validate(value)
    except ValidationError as exc:
        raise ParamsError(f"invalid params for node {node!r}: {exc}") from exc


def _record_llm_calls(index: DuckDBRunIndex, result: RunResult) -> None:
    """Write the run's model calls (cache hits excluded) to the index's `llm_calls` ledger."""
    for call in llm_calls_from_result(result.run_id, result):
        index.record_llm_call(call)


def run(spec: RunSpec, registry: NodeRegistry, **kwargs: Any) -> RunResult:
    """Synchronous wrapper around `arun` (`asyncio.run`); takes the same keyword arguments."""
    return asyncio.run(arun(spec, registry, **kwargs))
