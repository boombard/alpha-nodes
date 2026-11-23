---
id: TASK-2
title: M1.2 Node registry and plan building
status: To Do
assignee: []
created_date: '2026-11-23T08:02:41Z'
labels:
  - core
milestone: m-0
dependencies:
  - TASK-1
references:
  - documentation/design/core.md
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec: `documentation/design/core.md`, Graph section. Runs in parallel with task-3 and task-4, which touch disjoint files.

## Files
- Create: `packages/lensgraph/src/lensgraph/registry.py`, `packages/lensgraph/src/lensgraph/graph.py`
- Test: `packages/lensgraph/tests/test_registry.py`, `packages/lensgraph/tests/test_graph.py`, plus a `toy_registry` fixture **in the test modules** (do not edit `conftest.py`, task-3/4 run concurrently). Move the fixture into conftest in task-5.

## Interfaces
Consumes (task-1):
- `Node`, `CandidateRef`, `NodeKey`, `PlannedNode`, `ExecutionPlan`
- the toy nodes in `tests/toy/nodes.py`

Produces:
```python
class NodeRegistry:
    def register(self, cls: type[Node]) -> type[Node]   # usable as decorator; duplicate name -> ValueError
    def get(self, name: str) -> type[Node]              # missing -> UnknownNodeError
    def names(self) -> list[str]
class GraphError(ValueError): ...
class UnknownNodeError(GraphError); class CycleError(GraphError); class ScopeError(GraphError)
class DuplicateCandidateError(GraphError); class ParamsError(GraphError)
GraphRule = Callable[[Mapping[str, type[Node]]], None]   # raises GraphError
GRAPH_RULES: list[GraphRule]                              # module-level; later milestones append rules
def build_plan(targets: Sequence[str], registry: NodeRegistry, candidates: Sequence[CandidateRef], *,
               node_params: Mapping[str, Mapping[str, Any]] | None = None,
               replacements: Mapping[str, type[Node]] | None = None,
               run_id: str | None = None) -> ExecutionPlan
def to_mermaid(classes: Mapping[str, type[Node]]) -> str  # node-name level
def resolve_classes(targets, registry, replacements=None) -> dict[str, type[Node]]  # transitive closure
```
Semantics:
- **Resolution:** resolve the transitive closure of `targets` over `all_inputs()`. Apply each `replacements[name]` before resolving. A replacement whose `.name != name` raises `GraphError`.
- **Rules:** run every rule in `GRAPH_RULES` on the resolved classes.
- **Graph errors:**
  - **Cycle:** raises `CycleError` with the path in its message, e.g. `"a -> b -> a"`.
  - **Scope:** a `shared` node depending on a `candidate` node raises `ScopeError`.
  - **Duplicate candidate ids:** raise `DuplicateCandidateError`.
- **Instantiation:** each class is instantiated **once** with `cls.model_validate(node_params.get(name, {}))`.
  - A `ValidationError` becomes `ParamsError` naming the node.
  - A `node_params` key for a node that isn't in the resolved graph raises `ParamsError`.
- **Expansion:** shared nodes get one `NodeKey(name, None)`. Candidate nodes get one key per candidate. A candidate node's deps on shared nodes point at the shared key. `optional` = the names from `optional_inputs`.
- **Ordering:** `plan.nodes` is in a deterministic topological order: Kahn's algorithm with ties broken by name, then candidate order.
- **`run_id`:** default is `f"{utc:%Y%m%dT%H%M%S}-{uuid4().hex[:6]}"`.
- **`to_mermaid`:** starts with `flowchart LR`. Required edges are `a --> b`, optional edges `a -.-> b`, and shared nodes get `:::shared`.

## Steps
- [ ] Write the failing tests:
  - `test_register_duplicate_raises`
  - `test_get_unknown_raises`
  - `test_resolves_transitive_deps_only_for_targets`: targets `["growth_rate"]` with S1–S3 gives 1 `reference_panel` key + 3 × (`assay_raw`, `assay_clean`, `growth_rate`) = 10 nodes, and no `tox_notes`.
  - `test_shared_node_single_instance_and_deps_point_to_it`
  - `test_topological_order`: every dep key appears before its dependent in `plan.nodes`.
  - `test_cycle_detected_with_path`: two nodes defined in the test.
  - `test_shared_depends_on_candidate_raises`
  - `test_unknown_input_raises`
  - `test_params_applied_and_typo_rejected`: `{"growth_rate": {"window": 3}}` gives `.window == 3`; `{"growth_rate": {"windw": 3}}` raises `ParamsError` with `"growth_rate"` in the message.
  - `test_params_for_unresolved_node_rejected`
  - `test_replacement_swaps_implementation`
  - `test_replacement_name_mismatch_rejected`
  - `test_duplicate_candidate_ids_rejected`
  - `test_descendants`: `plan.descendants({"assay_clean"})` is the 3 `assay_clean` keys plus the 3 `growth_rate` keys.
  - `test_graph_rule_invoked`: append a rule that raises inside a `monkeypatch`ed `GRAPH_RULES`.
  - `test_to_mermaid_edges`: contains `assay_raw --> assay_clean`; a test-only node with an optional input renders `-.->`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_graph.py packages/lensgraph/tests/test_registry.py -q`. Expected: FAIL.
- [ ] Implement `registry.py` and `graph.py`.
- [ ] Run the tests above, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): node registry and plan building with validation`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 build_plan resolves only the transitive deps of targets, shared nodes once, candidate nodes per candidate
- [ ] #2 Cycles, scope violations, unknown inputs, duplicate candidates and bad params raise specific GraphError subclasses
- [ ] #3 Plan order is deterministic and topological; descendants() and to_mermaid() work
- [ ] #4 GRAPH_RULES hook lets later milestones add validation rules
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
