---
id: TASK-18
title: M3.1 Run config, brief, review and record contracts
status: To Do
assignee: []
created_date: '2026-11-23T23:51:00Z'
updated_date: '2026-11-24T00:02:47Z'
labels:
  - core
  - contracts
milestone: m-2
dependencies:
  - TASK-9
references:
  - documentation/design/core.md
type: feature
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Contracts task for M3. Sequential: the other M3 tasks build on these names. Spec: `documentation/design/core.md`, sections Run configuration, Artifact store and run index, Assessment brief and post-panel review, Reporting, and Verdicts and dossiers (Principles: no run ids in node outputs). Global constraints: `backlog/docs/doc-1 - Implementation-plan.md`.

## Files
- Create: `packages/lensgraph/src/lensgraph/config.py`, `packages/lensgraph/src/lensgraph/records.py`, `packages/lensgraph/tests/toy/registry.py`, `packages/lensgraph/tests/toy/toy_run.yaml`
- Modify:
  - `packages/lensgraph/src/lensgraph/verdict.py`: add `AssessmentBrief`, `ReviewPoint`, `DossierReview`.
  - `packages/lensgraph/src/lensgraph/store/base.py`: extend `RunIndex`.
  - `packages/lensgraph/src/lensgraph/store/memory.py`: in-memory implementations of the new `RunIndex` methods.
  - `packages/lensgraph/src/lensgraph/store/duckdb_index.py`: the new methods as stubs raising `NotImplementedError` (M3.2 implements them), so nothing silently returns None.
  - `packages/lensgraph/src/lensgraph/__init__.py`: exports.
  - `packages/lensgraph/pyproject.toml`: add `pydantic-settings` and `pyyaml`.
  - `packages/lensgraph/tests/conftest.py`: `toy_registry`/`ai_registry` fixtures use `toy.registry` (DRY; same behaviour).
- Test: `packages/lensgraph/tests/{test_config,test_records}.py`

## Interfaces
Consumes: `RunSpec`, `Panel`, `Dossier`, `Provenance`, `Flag`, `NodeRegistry`, `ProfileRegistry`, `LLMProfile`, toy nodes and `SafetyLens`.

Produces:
```python
# verdict.py  (frozen, extra="forbid", like the other verdict models)
class AssessmentBrief(BaseModel):
    purpose: str; horizon: str | None = None
    priorities: list[str] = []; out_of_scope: list[str] = []
    extra: dict[str, str] = {}                       # domain-specific facts
class ReviewPoint(BaseModel):
    text: str; cites: list[str] = Field(min_length=1)
    priority: str | None = None                      # must be one of brief.priorities when set
class DossierReview(BaseModel):
    summary: str
    fit: list[ReviewPoint] = []                      # fit to the brief
    gaps: list[ReviewPoint] = []                     # what evidence would change the view
    flags: list[Flag] = []                           # closed list, enforced by the reviewer node
    provenance: Provenance
# records.py
class DossierRecord(BaseModel):                      # built outside the graph, for exports and reports
    run_id: str; created_at: datetime; dossier: Dossier; review: DossierReview | None = None
class LLMCall(BaseModel):                            # one model call (all its retries) made in a run
    run_id: str; candidate: str | None; node: str; model: str
    attempts: int; input_tokens: int; output_tokens: int
    cost_usd: float | None                           # None when the model has no known price
# store/base.py: RunIndex gains
    def record_llm_call(self, call: LLMCall) -> None: ...
    def llm_calls(self, run_id: str) -> list[LLMCall]: ...
    def run_config(self, run_id: str) -> dict[str, Any]: ...      # the config stored by start_run
    def node_result(self, run_id: str, node: str, candidate: str | None) -> NodeResult | None: ...
# config.py
class Settings(BaseSettings):                        # env prefix LENSGRAPH_
    store_root: Path = Path(".lensgraph")
    local_model: str | None = None                   # LENSGRAPH_LOCAL_MODEL (read by llm.py from here later)
class ReportOptions(BaseModel):
    enabled: bool = True; out_dir: Path | None = None   # default <store_root>/reports/<run_id>
    max_rows: int = 200
class RunConfig(RunSpec):                            # extra="forbid" inherited
    registry: str                                    # "module:attr", a NodeRegistry or a zero-arg factory
    services: str | None = None                      # "module:attr", a mapping or a zero-arg factory
    brief: AssessmentBrief | None = None
    report: ReportOptions = ReportOptions()
    @classmethod
    def from_yaml(cls, path: Path) -> "RunConfig"
def load_object(ref: str) -> Any                     # "pkg.mod:attr"; calls it if it is a zero-arg callable that isn't a class
# tests/toy/registry.py
def build_registry() -> NodeRegistry                 # all toy nodes + GrowthLens + SafetyLens
def build_services() -> dict[str, Any]               # {"assays": FakeAssaySource(), "profiles": ProfileRegistry(...)} with a scripted
                                                     # FunctionModel behind a "test" profile, so the toy run is offline
```
Semantics:
- `RunConfig.from_yaml`: unknown keys are a `ValidationError` naming the key (no silent typos).
- `load_object`: a bad module or attribute raises `ImportError`/`AttributeError` naming the ref.
- `ReviewPoint.priority` is validated by the reviewer node (M3.3), not by the model, because the model doesn't know the brief.
- `toy_run.yaml`: S1 to S3, panel `[growth_lens, safety_lens]`, `nodes.safety_lens.profile: test`, a brief, registry `toy.registry:build_registry`, services `toy.registry:build_services`.

## Steps
- [ ] Write the failing tests:
  - `test_config.py`:
    - `test_run_config_from_yaml_roundtrip`: `toy_run.yaml` loads; `targets` empty and `panel` set.
    - `test_unknown_key_rejected`: an extra top-level key and an extra `report` key each raise naming the key.
    - `test_load_object_factory_and_attr`: a factory is called; a plain attribute is returned; a bad ref raises naming it.
    - `test_settings_env_prefix`: `LENSGRAPH_STORE_ROOT` sets `store_root` (monkeypatch env).
  - `test_records.py`:
    - `test_brief_and_review_models_frozen_and_strict`
    - `test_review_point_requires_cite`
    - `test_dossier_record_roundtrip_json`
    - `test_memory_index_llm_calls_and_config`: record two calls, read back in order; `run_config` returns the stored config; `node_result` finds a recorded result and returns None for a missing one.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_config.py packages/lensgraph/tests/test_records.py -q`. Expected: FAIL.
- [ ] Implement; make conftest's toy fixtures use `toy.registry`.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): M3 contracts: run config, brief, review and record models`.

Out of scope: DuckDB implementations of the new RunIndex methods (M3.2), the reviewer node (M3.3), the report (M3.4), the CLI (M3.5).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 RunConfig loads from YAML with unknown keys rejected; Settings reads LENSGRAPH_ env
- [ ] #2 AssessmentBrief, ReviewPoint, DossierReview, DossierRecord and LLMCall match Interfaces
- [ ] #3 RunIndex gains record_llm_call, llm_calls, run_config and node_result; in-memory implemented, DuckDB stubs raise NotImplementedError
- [ ] #4 Toy registry and services factories exist and conftest uses them; toy_run.yaml loads
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
Worker start failed 2026-11-24 at agent_readiness (dispatch ctx_706e5f4485ba): the launch command was mangled ('zsh: command not found: laude'). Worktree task-18 was created and left in place; no retry yet.
<!-- SECTION:NOTES:END -->
