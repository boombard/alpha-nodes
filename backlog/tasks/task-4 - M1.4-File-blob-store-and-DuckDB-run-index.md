---
id: TASK-4
title: M1.4 File blob store and DuckDB run index
status: Done
assignee: []
created_date: '2026-11-23T08:02:42Z'
updated_date: '2026-11-23T09:00:40Z'
labels:
  - core
milestone: m-0
dependencies:
  - TASK-1
references:
  - documentation/design/core.md
type: feature
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec: `documentation/design/core.md`, section Artifact store and run index. Runs in parallel with task-2 and task-3.

## Files
- Create: `packages/lensgraph/src/lensgraph/store/files.py`, `packages/lensgraph/src/lensgraph/store/duckdb_index.py`
- Test: `packages/lensgraph/tests/test_file_blob_store.py`, `packages/lensgraph/tests/test_duckdb_index.py` (use pytest's `tmp_path`)

## Interfaces
Consumes (task-1): `BlobStore`, `RunIndex`, `NodeResult`, `NodeKey`, `Failed`, `Absent`, `content_hash`; and `ToxNote` from `tests/toy/nodes.py`.

Produces:
```python
class FileBlobStore:      # implements BlobStore
    def __init__(self, root: Path) -> None      # blobs at root/<h[:2]>/<h>.<ext>
class DuckDBRunIndex:     # implements RunIndex
    def __init__(self, path: Path) -> None      # one connection; call from the event-loop thread only
```
Serialisation rules. There is **no pickle**:
- **`pd.DataFrame`:** written as `.parquet` via pyarrow, keeping the index, dtypes and an empty frame's columns.
- **Pydantic models:** written as `.json` with the envelope `{"type": "<module>:<QualName>", "data": model_dump(mode="json")}`, and re-imported on `get`.
- **Lists and dicts of models:** an envelope per item.
- **JSON-native values** (None, bool, int, float, str, and lists/dicts of those): written as `.json`.
- **numpy scalars:** converted to Python values first.
- **Anything else:** `TypeError` at `put`.
- **Hashing:** `put` returns `content_hash(value)` computed on the value as given, so equal values give the same hash, and a second `put` is a no-op.

DuckDB tables:
- `runs(run_id PK, config_json, started_at, finished_at, status)`
- `node_results(run_id, node, candidate, status, output_hash, memo_key, cache_hit, error, failure_json, duration_s, meta_json)`
- `memo(memo_key PK, output_hash, created_at)`, upserted so the latest write wins.

## Steps
- [ ] Write the failing tests:
  - `test_roundtrip_types`, parametrized over:
    - 1.5, 3, "s", None, [1.0, 2.0], {"a": 1}
    - `numpy.float64(2.5)`, which comes back as the float 2.5
    - an empty DataFrame with `float64`/`object` dtypes
    - a DataFrame with a tz-aware `DatetimeIndex`
    - `ToxNote(id="n1", text="x")`, `[ToxNote(...), ToxNote(...)]`
    - `Absent(reason="r")`

    For each, `get(put(v))` equals `v` (`pd.testing.assert_frame_equal` for frames).
  - `test_put_idempotent_and_hash_is_content_hash`
  - `test_unsupported_type_raises`: an arbitrary object raises `TypeError`.
  - `test_blob_persistence_across_instances`
  - `test_index_persistence_across_instances`: start a run, record, close, reopen; `node_results` and `lookup_memo` survive.
  - `test_memo_upsert_latest_wins`
  - `test_node_results_roundtrip`: a `NodeResult` with `failure` and `meta` comes back equal.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_file_blob_store.py packages/lensgraph/tests/test_duckdb_index.py -q`. Expected: FAIL.
- [ ] Implement `files.py` and `duckdb_index.py`.
- [ ] Run the tests above, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): file blob store and DuckDB run index`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 FileBlobStore round-trips frames (parquet), pydantic models and lists of them, JSON primitives; no pickle
- [x] #2 Unsupported types raise TypeError at put; put is idempotent and returns content_hash
- [x] #3 DuckDBRunIndex persists runs, node results and memo entries across instances
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run pytest` passes (whole workspace)
- [x] #2 `uv run ruff check` and `uv run pyright` are clean
- [x] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [x] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_e583b32596d6, worktree task-4

Back to In Progress: the human asked for the blob store's byte layer to move onto fsspec (FsspecBlobStore by URL; FileBlobStore and InMemoryBlobStore become thin subclasses). Sent to the worker.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_e583b32596d6, branch boom/task-4, 4 commits 1e96bd3..9469c6a): FileBlobStore (parquet for frames, JSON envelopes for models, no pickle; atomic writes) and DuckDBRunIndex (runs, node_results, memo upsert). ACs 1-3 met (test_roundtrip_types/frames/numpy_scalar, test_frames_are_parquet_and_models_json, test_unsupported_type_raises, test_put_idempotent_and_hash_is_content_hash, test_index_persistence_across_instances, test_memo_upsert_latest_wins, test_node_results_roundtrip). Review Focus 3 covered: empty typed frame, tz-aware index, numpy scalar, list of models, Absent. Coordinator re-ran checks: pytest 70 passed, ruff clean, pyright 0 errors.
Coordinator review, one fix round: start_run on an existing id now also clears that run's old node_results (they used to mix two attempts). An unwritable frame now raises TypeError and leaves no tmp file. Reviewed by hand; the code-review skill was not run.
Round 2 (asked for by the human): the byte layer moved onto fsspec. FsspecBlobStore(url, **storage_options) works on file://, memory:// or s3:// (with s3fs). FileBlobStore(root) and InMemoryBlobStore() are now thin subclasses, so TASK-5's interface is unchanged. In-memory blobs go through the real encoding and come back as copies, which closes TASK-1's open point about stored references. Local writes stay atomic (temp file then fs.mv); has/get probe the two known paths instead of listing. core.md updated. Blob tests are parametrized over the file and memory backends. Coordinator check: TASK-2, TASK-3 and TASK-4 merged together in a throwaway tree give 111 tests passing with -W error, ruff and pyright clean, and the TASK-3 race probe passes 200 of 200 on the new store.
Worker rulings: (1) DatetimeIndex.freq is not preserved by parquet. (2) A user dict with exactly the keys {type, data}, where type contains ':', decodes as a model envelope (spec-dictated format; rare misdecode). (3) Tuples, non-str dict keys, Series and ndarray raise TypeError at put. (4) DuckDBRunIndex.close() was added beyond Produces. (5) node_results are ordered by rowid.
Open points: s3:// is untested (no network in tests). fsspec's memory filesystem is process-global and never freed, so long-lived processes using InMemoryBlobStore grow. The frame TypeError message still says 'FileBlobStore:' (cosmetic). s3fs caches listings, so exists() may be stale across processes. Commit 1e96bd3 is not green alone (squash when landing). meta_json uses plain json.dumps, so non-JSON meta raises at record_node, while config uses default=str.
Landed 3eadbae..3eadbae on main (worker commits squashed into one at the human's request).
<!-- SECTION:FINAL_SUMMARY:END -->
