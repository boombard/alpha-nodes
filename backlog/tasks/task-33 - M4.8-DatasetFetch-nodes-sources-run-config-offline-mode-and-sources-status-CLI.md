---
id: TASK-33
title: >-
  M4.8 DatasetFetch nodes, sources run config, offline mode and sources status
  CLI
status: In Review
assignee: []
created_date: '2026-11-25T01:09:29Z'
updated_date: '2026-11-25T04:46:14Z'
labels:
  - core
milestone: m-3
dependencies:
  - TASK-30
references:
  - documentation/design/core.md
type: feature
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wire the source store into runs: a generic `DatasetFetch` node, a `sources:` section in run config, the store built by `arun` and injected as the `sources` service, `--offline`, and a `lensgraph sources status` command. Prove it on the toy domain. After M4.5. Spec: `documentation/design/core.md`, Source store, Memoization (fetch nodes are not memoized; the slice's hash keys downstream), Run configuration; `documentation/design/finance.md`, Providers ("Fetch nodes are generic").

## Files
- Create:
  - `packages/lensgraph/src/lensgraph/sources/node.py`: `DatasetFetch`, `DatasetFetchMany`
  - `packages/lensgraph/src/lensgraph/sources/catalog.py`: `SourceCatalog`, `ProviderContext`, `SourcesConfig`, `build_source_store`
  - `packages/lensgraph/tests/toy/sources_run.yaml`, `packages/lensgraph/tests/toy/sources_nodes.py` (toy fetch nodes + catalog object)
- Modify:
  - `packages/lensgraph/src/lensgraph/config.py`: `RunConfig.sources: SourcesConfig | None = None`
  - `packages/lensgraph/src/lensgraph/run.py`: build and inject the store; close it at the end
  - `packages/lensgraph/src/lensgraph/cli.py`: `run --offline`; `sources status`
  - `packages/lensgraph/src/lensgraph/sources/__init__.py`, `packages/lensgraph/src/lensgraph/__init__.py`: exports
  - `documentation/design/core.md`: Run configuration (sources section, `--offline`, `sources status`)
- Test: `packages/lensgraph/tests/{test_source_node,test_sources_e2e}.py`; extend `test_cli.py`

## Interfaces
Consumes: `DuckDBSourceStore`, `SourceSlice`, `Dataset`, `Provider`, `RateLimitPolicy`, `Clock`, `SystemClock` (M4.1–M4.5); `FetchNode`, `NodeContext`, `RunConfig`, `arun`, `load_object`, the CLI.

Produces:
```python
# sources/node.py
class DatasetFetch(FetchNode):
    """Per-candidate read of one dataset through `ctx.services["sources"]`; subclasses set `name` and `dataset`."""
    dataset: ClassVar[str]
    output: ClassVar[Any] = pd.DataFrame
    lookback_days: int | None = None        # axis "date": window ending at ctx.as_of or the store clock's today
    entity_attr: str | None = None          # take the entity from candidate.attrs[...] instead of candidate.id
    include_rejected: bool = False
    async def run(self, ctx: NodeContext) -> pd.DataFrame   # the slice frame (canonical + fact meta columns)
class DatasetFetchMany(FetchNode):
    """Shared-scope read of one dataset for a fixed entity list (e.g. FX rates); one `ensure` call, so batching applies."""
    scope: ClassVar = "shared"
    dataset: ClassVar[str]
    output: ClassVar[Any] = pd.DataFrame
    entities: list[str]
    lookback_days: int | None = None
    async def run(self, ctx: NodeContext) -> pd.DataFrame   # concatenated slices, `entity` column, sorted
# sources/catalog.py
class ProviderContext(BaseModel):       # what a provider factory gets; arbitrary_types_allowed
    cache_dir: Path                       # <store_root>/provider_cache/<provider name>
    clock: Clock
class SourceCatalog(BaseModel):         # a domain's datasets and provider factories; arbitrary_types_allowed
    datasets: dict[str, Dataset]
    providers: dict[str, Callable[[ProviderContext], Provider]]
class SourcesConfig(BaseModel):         # extra="forbid"; the `sources:` section of a run YAML
    catalog: str                          # "module:attr" of a SourceCatalog (or zero-arg factory)
    providers: dict[str, list[str]]       # dataset -> provider names, primary first
    offline: bool = False
    limits: dict[str, RateLimitPolicy] = {}   # provider name -> policy override
def build_source_store(cfg: SourcesConfig, store_root: Path, blobs: BlobStore, *,
                       clock: Clock | None = None, offline: bool | None = None) -> DuckDBSourceStore
    # <store_root>/sources.duckdb; unknown dataset or provider names raise ParamsError naming them
```
Semantics:
- `arun`: when `spec` is a `RunConfig` with `sources`, build the store (unless `services` already has `"sources"`, which wins; tests use that) and close it when the run ends, aborted or not.
- `DatasetFetch` on a candidate whose slice is `empty` returns the empty frame (failure semantics: legitimate empty is not an error). `SourceUnavailable` propagates, so the node fails and dependents skip.
- CLI: `lensgraph run CONFIG --offline` overrides `sources.offline`. `lensgraph sources status [--store PATH] [--dataset NAME] [--suspect]` prints, per dataset and provider: entities, covered ranges, attempts by kind, and suspect/rejected row counts; `--suspect` lists suspect rows (entity, key, reasons). Exit 0. It reads the store file only, no catalog needed.
- A run with `targets` and no panel builds its report without error (fix the view only if it fails; keep that change minimal and tested).

## Steps
- [ ] Write the failing tests:
  - `test_source_node.py`:
    - `test_dataset_fetch_window_ends_at_as_of_or_today`
    - `test_dataset_fetch_entity_attr`
    - `test_empty_slice_is_empty_frame_not_failure`
    - `test_source_unavailable_fails_node_and_skips_dependents` (via `arun` with an offline store)
    - `test_fetch_many_one_ensure_call_batches` (bulk fake: 7 entities → 2 calls)
    - `test_downstream_reruns_only_when_slice_changes`: second run with no new data → downstream memo hit; after the fake restates a value → downstream reruns.
  - `test_sources_e2e.py`:
    - `test_two_runs_fetch_only_once`: `toy/sources_run.yaml` run twice through `arun` on one store root; the fake's `calls` only grow in run 1.
    - `test_offline_rerun_serves_from_store`
    - `test_unknown_provider_name_is_params_error`
  - `test_cli.py`: `test_cli_offline_flag`, `test_cli_sources_status_lists_attempts_and_suspect`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_source_node.py packages/lensgraph/tests/test_sources_e2e.py -q`. Expected: FAIL.
- [ ] Implement; update core.md.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): DatasetFetch nodes, sources run config, offline mode and sources status CLI`.

Out of scope: finance nodes and config (M4.9).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 DatasetFetch and DatasetFetchMany read through the sources service; empty slices are empty frames; SourceUnavailable fails the node
- [ ] #2 RunConfig.sources builds the DuckDB source store under the store root; unknown dataset or provider names are ParamsError
- [ ] #3 Toy config run twice calls the provider only in run 1; downstream memo hits until the slice changes; offline rerun serves from the store
- [ ] #4 lensgraph run --offline and lensgraph sources status [--suspect] work; core.md Run configuration updated
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_595ec695149a, worktree task-33

Second fix round sent at the human's request (empty entities, store-leak test, dtype check, hashing scan cost).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: DatasetFetch/DatasetFetchMany (sources/node.py), SourceCatalog/ProviderContext/SourcesConfig/build_source_store (sources/catalog.py), RunConfig.sources wired into arun (built, injected, closed on every path), `lensgraph run --offline`, `lensgraph sources status [--dataset] [--suspect]`, core.md Run configuration updated. Commits c2dde13 + b6dec99 (review fixes). pytest 520 passed, ruff clean, pyright 0 errors.

Coordinator review: ACs 1-4 met. One feedback round, all applied: window docstring corrected (lookback_days+1 inclusive days); DatasetFetchMany all-empty result keeps the dataset's columns; source store can no longer leak its file lock if index setup fails; `sources status --dataset <unknown>` is a CliError.

Out-of-Files edits (approved mid-task): hashing.py + test_hashing.py (list/ndarray cells hash by canonical sorted-key JSON so a Parquet round trip hashes equal; frames without list cells keep a pinned identical digest); duckdb_store.py read-only `clock` property.

Rulings to check: window = [end - lookback_days, end] inclusive; lookback_days None = no interval; build_source_store builds only datasets listed in sources.providers and also rejects unknown limits names, empty provider chains, bad catalog refs; --offline without sources is a CLI error; sources status counts rows over all stored versions, exits 2 when no sources.duckdb; ctx.as_of is never set by the executor today, so live runs use the store clock.

Open points: DatasetFetchMany with an empty `entities` list raises IndexError (entities[0]); no test for the store-leak path; empty-frame test checks columns, not dtypes; hashing scans every object column per hash (Python-level map), a possible cost on big frames.
<!-- SECTION:FINAL_SUMMARY:END -->
