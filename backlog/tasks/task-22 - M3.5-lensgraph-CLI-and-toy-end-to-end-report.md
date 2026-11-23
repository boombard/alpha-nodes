---
id: TASK-22
title: M3.5 lensgraph CLI and toy end-to-end report
status: To Do
assignee: []
created_date: '2026-11-23T23:51:15Z'
labels:
  - core
milestone: m-2
dependencies:
  - TASK-21
references:
  - documentation/design/core.md
type: feature
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
CLI and toy end-to-end. Closes M3. Spec: `documentation/design/core.md`, Run configuration and Reporting; milestone demo gate.

## Files
- Create: `packages/lensgraph/src/lensgraph/cli.py`, `packages/lensgraph/tests/test_cli.py`
- Modify:
  - `packages/lensgraph/pyproject.toml`: `[project.scripts] lensgraph = "lensgraph.cli:main"`.
  - `packages/lensgraph/src/lensgraph/run.py`: `RunSpec` gains `profile_override: str | None = None` (applied to every AI node in the plan, i.e. `AINode` subclasses and `DossierReviewer`, by setting their `profile` param unless the config sets one explicitly), `arun` accepts a `RunConfig`, storing its resolved dump as the run config, and defaults targets to `spec.panel.targets()` (adds the reviewer when set).
  - `packages/lensgraph/src/lensgraph/llm.py`: read the local model through `Settings().local_model` instead of `os.environ` (same env var, same error).
  - `documentation/design/core.md`: Run configuration (registry/services refs, brief, report options, CLI usage).
- Test: `packages/lensgraph/tests/test_cli.py`

## Interfaces
Consumes: `RunConfig`, `Settings`, `load_object` (M3.1), `build_report` (M3.4), `arun`, `RunAborted`.

Produces:
```python
# cli.py (argparse, no extra dependency)
def main(argv: Sequence[str] | None = None) -> int
#   lensgraph run CONFIG.yaml [--store PATH] [--invalidate NODE ...] [--no-cache] [--profile NAME]
#                             [--no-report] [--path DIR ...]
#   lensgraph report RUN_ID [--store PATH] [--out DIR]
```
Semantics:
- **`--path DIR`** prepends to `sys.path` before resolving `registry`/`services` refs (the toy domain lives under `packages/lensgraph/tests`).
- **Store root:** `--store` beats `LENSGRAPH_STORE_ROOT` beats the `Settings` default.
- **Flags override the config:** `--invalidate` adds to `invalidate`, `--no-cache` sets `no_cache`, `--profile` sets `profile_override`.
- **Output:** prints the run id, the store root and the report path (`<store>/reports/<run_id>/index.html` unless `report.out_dir` is set).
- **Exit codes:** 0 on an ok run (even when some nodes failed: that is data), 2 on a config or params error (message on stderr, no traceback), 3 on `RunAborted` (report still built from what finished).
- **`lensgraph report`** rebuilds a report for an existing run from the index and blobs alone.

## Steps
- [ ] Write the failing tests (call `main([...])` in-process with `tmp_path` stores; no subprocess needed):
  - `test_cli_run_toy_writes_report`: `run toy_run.yaml --path <tests dir> --store <tmp>` returns 0; the report index exists; stdout names the run id.
  - `test_cli_rerun_all_cache_hits`: a second run's node results are cache hits for every memoizable node.
  - `test_cli_invalidate_and_no_cache`
  - `test_cli_profile_override_applies_to_ai_nodes`: `--profile test2` (a second scripted profile) changes AI node memo keys only.
  - `test_cli_config_error_exit_2`: an unknown YAML key gives exit 2 and a one-line error naming the key.
  - `test_cli_report_rebuilds`
  - `test_local_model_via_settings`: `LENSGRAPH_LOCAL_MODEL` still resolves the local profile.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_cli.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): lensgraph CLI and toy end-to-end report`.

**M3 demo gate (for the human):** run `uv run lensgraph run packages/lensgraph/tests/toy/toy_run.yaml --path packages/lensgraph/tests` and paste its output (run id, report path) into the final summary. The human opens the report and drills from a claim to its cited data.

Out of scope: campaigns (M7), as-of runs (M8), a web frontend.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 lensgraph run <yaml> runs the toy panel with reviewer and writes the report; rerun is all cache hits
- [ ] #2 --invalidate, --no-cache and --profile override the config; config errors exit 2 without a traceback
- [ ] #3 lensgraph report rebuilds a report from the index and blobs alone
- [ ] #4 M3 demo gate output recorded
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
