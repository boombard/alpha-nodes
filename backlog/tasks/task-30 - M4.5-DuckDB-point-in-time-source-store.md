---
id: TASK-30
title: M4.5 DuckDB point-in-time source store
status: To Do
assignee: []
created_date: '2026-11-25T01:09:28Z'
labels:
  - core
milestone: m-3
dependencies:
  - TASK-27
  - TASK-28
references:
  - documentation/design/core.md
type: feature
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The point-in-time source store: DuckDB for raw-response records, append-only facts, coverage states and the attempt log; raw payloads in the existing `BlobStore`. It composes coverage planning (M4.2) and the scheduler (M4.3). After M4.2 and M4.3. Spec: `documentation/design/core.md`, Source store (all of it, plus the TTL semantics M4.2 wrote); `documentation/design/lessons.md` (caching lessons). DuckDB table layouts are left to the builder; describe them in the module docstring. One constraint: **facts are stored in one table per dataset, created from `Dataset.frame_schema` with typed columns** (floats as `DOUBLE`, dates as `DATE`/`TIMESTAMP`, ints as `BIGINT`), plus the fact meta columns (`repairs`/`quality_reasons` as `VARCHAR[]`). Never rows as JSON text in a generic table: it is several times larger, must be parsed on every query, and makes the version comparison depend on float formatting. The code stays generic by building the table from the schema.

## Files
- Create: `packages/lensgraph/src/lensgraph/sources/duckdb_store.py`
- Modify: `packages/lensgraph/src/lensgraph/sources/__init__.py` (export `DuckDBSourceStore`)
- Test: `packages/lensgraph/tests/test_source_store.py` (+ fixtures in `packages/lensgraph/tests/conftest.py` if shared later)

## Interfaces
Consumes: everything in `sources/` (M4.1–M4.3); `BlobStore`, `InMemoryBlobStore`/`FileBlobStore` (store/); toy datasets and fake providers.

Produces:
```python
class DuckDBSourceStore(SourceStore):
    def __init__(
        self, path: Path | str,                 # ":memory:" allowed
        blobs: BlobStore,                       # raw payloads (content-addressed)
        datasets: Mapping[str, Dataset],
        providers: Mapping[str, Sequence[Provider]],   # dataset -> fallback chain, primary first
        *, clock: Clock | None = None,          # default SystemClock()
        offline: bool = False,
        policy_overrides: Mapping[str, RateLimitPolicy] = {},   # provider name -> policy replacing the declared one
    ) -> None
    def close(self) -> None
```
Semantics (each is pinned by a test below):
- `get` = `ensure` for one entity, then `query`. One `ProviderLimiter` per provider name per store.
- **Fallback is per entity**: try the chain in order; a provider that is `known_empty` or answers `empty` passes to the next. The slice comes from one provider only (no mixing). All empty → `SourceSlice(empty=True, provider=None)` with an empty frame of the right columns.
- **Persistence per outcome**: in `on_outcome`, write the raw response (payload to blobs, record to DuckDB), the attempt, the new coverage state, and the normalised facts, in one DuckDB transaction. A later `GlobalFailure` leaves these in place.
- **Facts are append-only**: a row is compared with the latest version of its key on its canonical values **and** its labels (`repairs`, `quality`, `quality_reasons`); bookkeeping columns (`fetch_id`, `first_seen_at`, `normaliser_version`) are not compared. A row equal on both adds nothing; a row that differs in either adds a version (`first_seen_at = now`), so a relabel alone (e.g. a new check marking a row `suspect`) is kept in the history. Rows after the outcome's `settled_through` are dropped and an `unsettled` attempt is logged for that tail. `known_at` from the normaliser, else `first_seen_at`.
- **Queries**: latest version per key with `known_at < as_of + 1 day` (as_of is a date; the cut-off is the end of that UTC day); `as_of=None` means latest. `rejected` rows excluded unless `include_rejected`; `suspect` rows served with their reasons. Interval filter on the axis column.
- **`error` after retries** raises `SourceUnavailable` naming dataset, entity and provider; nothing is cached.
- **`restated_before`**: applied through `apply_outcome`, and `get` replans once in the same call, so the restated history is refetched immediately.
- **Offline**: no provider is called; any gap (or due snapshot) raises `SourceUnavailable`; covered data is served.
- **`renormalise(dataset, provider)`**: re-runs `provider.normalise` over every stored raw response for that pair (oldest first) and appends versions where values or labels changed (same rule as above), stamped with the new `normaliser_version`. Never calls `fetch`. Each call is logged in a `renormalisations` table (dataset, provider, normaliser_version, started/finished, raw responses read, rows written); this is store-internal, not part of the `SourceStore` protocol.
- `pit_reliable` on slices comes from the serving provider's capabilities.
- All DuckDB access happens on the event-loop thread (providers run in threads but never touch the DB).

## Steps
- [ ] Write the failing tests (toy datasets, fake providers, `FakeClock`, `InMemoryBlobStore`, a `tmp_path` DuckDB file where persistence matters):
  - `test_second_get_makes_no_provider_calls`
  - `test_mid_range_hole_fetches_only_the_hole`
  - `test_rows_after_settled_not_stored_and_tail_logged`
  - `test_unchanged_refetch_adds_no_version`
  - `test_relabel_only_adds_version`: same value, different `quality` → a new version; `as_of` before it sees the old label.
  - `test_changed_value_adds_version_and_as_of_sees_old`: restate one day after the clock moves; `as_of` before the restatement returns the old value, `as_of=None` the new one.
  - `test_as_of_excludes_later_known_at`
  - `test_rejected_excluded_suspect_served_with_reasons`
  - `test_fallback_to_second_provider_on_empty`: entity unknown to `fake` is served by `fake_bulk`; `provider` on the slice says so; a second get calls neither (empty is cached for `fake`).
  - `test_all_providers_empty_gives_empty_slice`
  - `test_error_raises_source_unavailable_and_is_not_cached`
  - `test_global_failure_keeps_finished_items_and_resumes`: `ensure` over 4 entities where the 3rd hits the unreachable threshold → `GlobalFailure`; a new store on the same file fetches only the unfinished entities.
  - `test_ensure_batches_by_max_batch`: 7 entities → 2 calls on `fake_bulk`.
  - `test_restated_before_refetches_history_in_same_get`
  - `test_snapshot_refetched_after_ttl`
  - `test_offline_serves_covered_and_raises_on_gap`
  - `test_renormalise_rebuilds_without_fetch`: bump the fake's normaliser version and its spike threshold; renormalise; facts reflect it (the spike rows' new labels are new versions even though od600 is unchanged); `calls` unchanged; raw responses count unchanged; one `renormalisations` row records the run.
  - `test_policy_override_replaces_declared_policy`
  - `test_facts_table_columns_are_typed`: the `assays` facts table has `od600` as `DOUBLE` and `day` as a date/timestamp type, not `VARCHAR`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_source_store.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): DuckDB point-in-time source store`.

Out of scope: the fetch node, run wiring and CLI (M4.8); any finance dataset.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Second get makes no provider calls; only gaps are fetched; rows after settled_through are not stored and the tail is logged unsettled
- [ ] #2 Facts are append-only with versions on change; as-of queries return the latest version known by the end of that day; rejected excluded, suspect served
- [ ] #3 Per-entity provider fallback on empty; error raises SourceUnavailable uncached; finished items survive GlobalFailure and a new store resumes from gaps
- [ ] #4 restated_before refetches in the same get; offline serves or raises; renormalise rebuilds facts from raw without fetching
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
