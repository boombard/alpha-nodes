---
id: TASK-4
title: M1.4 File blob store and DuckDB run index
status: To Do
assignee: []
created_date: '2026-11-23T08:02:42Z'
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
- [ ] #1 FileBlobStore round-trips frames (parquet), pydantic models and lists of them, JSON primitives; no pickle
- [ ] #2 Unsupported types raise TypeError at put; put is idempotent and returns content_hash
- [ ] #3 DuckDBRunIndex persists runs, node results and memo entries across instances
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
