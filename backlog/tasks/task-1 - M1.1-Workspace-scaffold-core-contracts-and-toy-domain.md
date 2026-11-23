---
id: TASK-1
title: M1.1 Workspace scaffold, core contracts and toy domain
status: In Review
assignee: []
created_date: '2026-11-23T08:02:41Z'
updated_date: '2026-11-23T08:19:21Z'
labels:
  - core
  - contracts
milestone: m-0
dependencies: []
references:
  - documentation/design/core.md
priority: high
type: feature
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Contracts task for M1. Sequential: every other M1 task builds on these names. Spec: `documentation/design/core.md` (Pydantic-first, Nodes, Memoization), `documentation/design/overview.md` (Repository layout). Global constraints: `backlog/docs/doc-1 - Implementation-plan.md`.

## Files
- Create: `pyproject.toml` (uv workspace root). `[tool.uv.workspace] members = ["packages/*"]`, plus a dev dependency group with pytest>=8, pytest-asyncio, ruff and pyright.
  - `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`, `testpaths = ["packages"]`.
  - ruff: `line-length = 100`.
  - pyright: `typeCheckingMode = "basic"`.
- Create: `.python-version` containing `3.13`. Modify: `.gitignore` to add `.venv/`, `__pycache__/`, `.lensgraph/`, `spikes/**/.spike_state/`.
- Create: `packages/lensgraph/pyproject.toml`. Name `lensgraph`, `requires-python = ">=3.13,<3.14"`, src layout. Deps: pydantic>=2.14, pandas>=3.1, pandera[pandas]>=0.36, numpy, pyarrow, duckdb.
- Create: `packages/lensgraph/src/lensgraph/{__init__,types,node,plan,hashing}.py`, `executor/{__init__,base}.py`, `store/{__init__,base,memory}.py`.
- Create (toy domain, shared by all later core tests): `packages/lensgraph/tests/conftest.py`, `tests/toy/{__init__,sources,nodes}.py`.
- Test: `packages/lensgraph/tests/{test_types,test_node,test_hashing,test_memory_store}.py`.

## Interfaces (Produces): exact names other tasks rely on
```python
# types.py   (all models: ConfigDict(frozen=True, extra="forbid"))
Scope = Literal["shared", "candidate"]
class CandidateRef(BaseModel): id: str; attrs: dict[str, str | int | float | bool | None] = {}
class Absent(BaseModel): reason: str          # legitimately missing / optional upstream failed
class Failed(BaseModel): origin: str; candidate: str | None; error: str   # origin = node where it arose
class GlobalFailure(Exception): ...            # run must abort
class UpstreamFailed(Exception): failure: Failed   # __init__(self, failure)
class ContractViolation(Exception): ...

# node.py
class NodeContext(BaseModel):                 # arbitrary_types_allowed
    run_id: str; candidate: CandidateRef | None; as_of: date | None = None
    services: dict[str, Any] = {}; input_hashes: dict[str, str] = {}
class Node(BaseModel):                         # frozen, extra="forbid"; fields = params
    name: ClassVar[str]; inputs: ClassVar[dict[str, str]] = {}; optional_inputs: ClassVar[dict[str, str]] = {}
    output: ClassVar[Any] = object             # type | BaseModel subclass | pandera DataFrameModel subclass
    scope: ClassVar[Scope] = "candidate"; version: ClassVar[str] = "1"; resource: ClassVar[str | None] = None
    memoize: ClassVar[bool] = True; hash_source: ClassVar[bool] = True; consumes_verdicts: ClassVar[bool] = False
    def run(self, ctx: NodeContext, **inputs: Any) -> Any: ...        # may be `async def`
    def on_upstream_failure(self, ctx: NodeContext, failure: Failed) -> Any: raise UpstreamFailed(failure)
    def memo_salt(self, services: Mapping[str, Any]) -> str: return ""
    def check_inputs(self, **inputs: Any) -> None: return None   # stricter-than-producer checks; raise ContractViolation
    def validate_output(self, value: Any) -> Any                      # raises ContractViolation
    @classmethod
    def code_version(cls) -> str               # sha256(version [+ inspect.getsource(cls) if hash_source])[:16]
    @classmethod
    def all_inputs(cls) -> dict[str, str]      # inputs | optional_inputs
class FetchNode(Node): memoize = False; hash_source = False
class TransformNode(Node): ...
class CalcNode(Node): ...

# plan.py
class NodeKey(BaseModel): name: str; candidate: str | None      # frozen/hashable; __str__ -> "name" | "name[cand]"
class PlannedNode(BaseModel): key: NodeKey; node: Node; deps: dict[str, NodeKey]; optional: frozenset[str]
class ExecutionPlan(BaseModel):
    run_id: str; candidates: list[CandidateRef]; nodes: dict[NodeKey, PlannedNode]   # insertion order is topological
    def descendants(self, names: set[str]) -> set[NodeKey]      # keys of named nodes + everything downstream
NodeStatus = Literal["ok", "failed", "skipped", "recovered"]
class NodeResult(BaseModel):
    key: NodeKey; status: NodeStatus; output_hash: str | None = None; memo_key: str | None = None
    cache_hit: bool = False; error: str | None = None; failure: Failed | None = None
    duration_s: float = 0.0; meta: dict[str, Any] = {}
class RunResult(BaseModel):
    run_id: str; status: Literal["ok", "aborted"]; results: dict[NodeKey, NodeResult]
    values: dict[NodeKey, Any] = Field(default_factory=dict, exclude=True)

# hashing.py
def content_hash(value: Any) -> str            # sha256 hex, stable across processes
def memo_key(node: Node, input_hashes: Mapping[str, str], candidate_id: str | None, salt: str = "") -> str

# executor/base.py
class Executor(Protocol):
    async def execute(self, plan: ExecutionPlan, blobs: "BlobStore", index: "RunIndex", *,
                      services: Mapping[str, Any] | None = None,
                      bypass_memo: AbstractSet[NodeKey] = frozenset()) -> RunResult: ...
class RunAborted(Exception): result: RunResult; cause: BaseException   # __init__(self, result, cause)

# store/base.py
class BlobStore(Protocol):
    def put(self, value: Any) -> str: ...      # returns content_hash(value); idempotent
    def get(self, h: str) -> Any: ...; def has(self, h: str) -> bool: ...
class RunIndex(Protocol):
    def start_run(self, run_id: str, config: Mapping[str, Any]) -> None: ...
    def finish_run(self, run_id: str, status: str) -> None: ...
    def record_node(self, run_id: str, result: NodeResult) -> None: ...
    def lookup_memo(self, memo_key: str) -> str | None: ...
    def save_memo(self, memo_key: str, output_hash: str) -> None: ...
    def node_results(self, run_id: str) -> list[NodeResult]: ...
# store/memory.py
class InMemoryBlobStore(BlobStore); class InMemoryRunIndex(RunIndex)
```
Rules:
- `validate_output` behaviour depends on what `output` is:
  - a pandera `DataFrameModel` subclass: `output.validate(value)`
  - a pydantic model class: `isinstance`, else `model_validate`
  - any other type: `isinstance`

  `object` accepts anything. Any failure is re-raised as `ContractViolation` with the node name.
- `content_hash` per value type:
  - **DataFrame:** column names, dtypes, and `pd.util.hash_pandas_object(df, index=True)`.
  - **BaseModel:** fully-qualified class name plus `model_dump_json()`.
  - **Containers:** dict keys are sorted; list/tuple order is kept.
  - **Distinctions:** `None` and `Absent` hash differently. NaN hashes stably.
- `memo_key` hashes the node name, `"fetch"` (when `hash_source` is False) or `code_version()`, `node.model_dump_json()`, the sorted `input_hashes`, `candidate_id` and `salt`.

## Toy domain (`tests/toy/`): "strains", deliberately non-finance
- `sources.py`: `class FakeAssaySource` records every call in `self.calls: list[str]`. Methods:
  - `assays(strain) -> pd.DataFrame`: columns `time_h` and `od600`, 10 rows, seeded by strain. S3 returns a frame **without** `od600`.
  - `reference() -> pd.DataFrame`
  - `tox_notes(strain) -> list[ToxNote]`: S2 returns `[]`.
  - `fail_for: set[str]`: strains whose calls raise `GlobalFailure`.
- `nodes.py`:
  - `class ToxNote(BaseModel): id: str; text: str`
  - `class AssaySchema(pa.DataFrameModel)`: `time_h >= 0`, `od600 > 0` (floats). Import with `import pandera.pandas as pa`.
  - Nodes:
    - `ReferencePanel(FetchNode)`: name `reference_panel`, scope `shared`.
    - `AssayRaw(FetchNode)`: name `assay_raw`.
    - `AssayClean(TransformNode)`: name `assay_clean`, inputs `{"raw": "assay_raw"}`, output `AssaySchema`. It has the field `required_columns: list[str] = ["time_h", "od600"]`, and its `check_inputs` raises `ContractViolation` listing any missing columns in `raw`. This is the "tweak required columns from config" case.
    - `GrowthRate(CalcNode)`: name `growth_rate`, field `window: int = 5`, inputs `{"assay": "assay_clean", "reference": "reference_panel"}`, output `float`.
    - `ToxNotes(FetchNode)`: name `tox_notes`, output `list`.
  - Fetch nodes read the source from `ctx.services["assays"]`.
- `conftest.py` fixtures: `toy_source`, `toy_candidates` (S1, S2, S3 as `CandidateRef`), and `toy_services(toy_source) -> {"assays": toy_source}`.

## Steps
- [ ] Scaffold the workspace and run `uv sync`. Expected: `uv run pytest` exits 5 (no tests collected).
- [ ] Write the failing tests:
  - `test_types.py`:
    - `test_node_key_str_and_hashable`: `str(NodeKey(name="a", candidate="S1")) == "a[S1]"`, and the key works as a dict key.
    - `test_failed_is_frozen`
  - `test_node.py`:
    - `test_output_contract_pandera_rejects_missing_column`: `AssayClean().validate_output(<S3 frame>)` raises `ContractViolation` mentioning `assay_clean`.
    - `test_output_contract_type_mismatch`: `GrowthRate().validate_output("x")` raises.
    - `test_params_are_fields_and_unknown_rejected`: `GrowthRate.model_validate({"window": 7}).window == 7`, and `{"windw": 7}` raises `ValidationError`.
    - `test_code_version_changes_with_version_classvar`
    - `test_fetch_code_version_ignores_source`: two `FetchNode` subclasses with the same name and version but different bodies give the same `code_version()`.
    - `test_default_on_upstream_failure_raises`: raises `UpstreamFailed`.
    - `test_check_inputs_required_columns_param`: `AssayClean().check_inputs(raw=<S3 frame>)` raises with `"od600"` in the message, and `AssayClean(required_columns=["time_h"]).check_inputs(raw=<S3 frame>)` passes.
  - `test_hashing.py`:
    - `test_frame_hash_stable_and_order_sensitive`: equal frames give equal hashes; reordered rows differ; `astype("float32")` differs.
    - `test_model_hash_includes_type`
    - `test_dict_key_order_irrelevant`
    - `test_none_vs_absent_differ`
    - `test_memo_key_changes_with_params_inputs_candidate_salt`
    - `test_memo_key_fetch_ignores_source`
  - `test_memory_store.py`:
    - `test_blob_roundtrip_and_has`
    - `test_memo_lookup_and_overwrite`
    - `test_node_results_listed_per_run`
- [ ] Run them: `uv run pytest packages/lensgraph -q`. Expected: FAIL (ImportError).
- [ ] Implement the interfaces above.
- [ ] Run `uv run pytest packages/lensgraph -q && uv run ruff check && uv run pyright`. Expected: all pass, clean.
- [ ] Commit: `feat(lensgraph): workspace scaffold, node/plan/store contracts, toy domain`.

Out of scope: graph building, executor, persistent stores.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 uv workspace with packages/lensgraph syncs on Python 3.13 and pytest/ruff/pyright run
- [ ] #2 types, node, plan, hashing, executor/base and store/base+memory expose exactly the names in Interfaces
- [ ] #3 Node params are pydantic fields; unknown params rejected; output contracts raise ContractViolation
- [ ] #4 content_hash and memo_key are stable and sensitive to params, inputs, candidate and salt; fetch keys ignore source
- [ ] #5 Toy strain domain (S1-S3) with fake counted source available to all later tests
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
Worker: dispatch ctx_7f85090a0f4c, worktree task-1
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_7f85090a0f4c, branch boom/task-1, 4 commits 81ff0a8..682ef24): uv workspace scaffold; lensgraph types/node/plan/hashing/executor.base/store.base+memory; toy strain domain S1-S3. ACs 1-5 met. Coordinator re-ran checks: pytest 27 passed, ruff clean, pyright 0 errors.
Coordinator review: interfaces match the spec. One fix round applied: content_hash no longer falls back to repr (it handles Series/ndarray/date/bytes and raises TypeError otherwise); validate_output no longer leaks AttributeError; InMemoryRunIndex.finish_run tolerates an unknown run; pytest uses importlib mode with pythonpath for toy.
Open points (spec-dictated or deferred): (1) memo_key uses the literal 'fetch' when hash_source=False, so a version bump on a non-source-hashed memoized node does not invalidate it. (2) RunResult/ExecutionPlan dicts keyed by NodeKey are not JSON-serialisable. (3) memo_key uses node.model_dump_json(), which is unstable for set/frozenset params. (4) InMemoryBlobStore stores references, not copies. (5) Object-dtype ndarrays and the unframed raw bytes in the bytes branch are weak spots in hashing. (6) Commit 427478b has a broken hashing.py that 32356fe fixes; squash on landing. (7) Worker rulings: 1 and 1.0 hash differently; an output=float node rejects int.
<!-- SECTION:FINAL_SUMMARY:END -->
