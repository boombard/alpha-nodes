---
id: TASK-22
title: M3.6 lensgraph CLI and toy end-to-end report
status: To Do
assignee: []
created_date: '2026-11-23T23:51:15Z'
updated_date: '2026-11-24T01:36:51Z'
labels:
  - core
milestone: m-2
dependencies:
  - TASK-24
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
Consumes: `RunConfig`, `Settings`, `load_object` (M3.1), `build_run_view` and `write_run_view` (TASK-21), `install_app` (TASK-24), `arun`, `RunAborted`.

**Report = app + data (changed 2026-11-24):** writing a report means `install_app(out_dir)` plus `write_run_view(build_run_view(...), out_dir)`, giving `index.html`, `run.json` and `data/run.js`. There is no Jinja report.

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
  - `test_cli_run_toy_writes_report`: `run toy_run.yaml --path <tests dir> --store <tmp>` returns 0; the report folder has `index.html`, `run.json` and `data/run.js`; `run.json` validates as `RunView`; stdout names the run id.
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

**E2E smoke test (added 2026-11-24):** add Playwright to `packages/lensgraph-ui` (devDependency, `playwright.config.ts` with `testDir: "tests/e2e"`, a `pnpm e2e` script, Chromium only). One test, `tests/e2e/report.spec.ts`: generate the toy report with the CLI into a temp dir (a Playwright `globalSetup` running `uv run lensgraph run ... --store <tmp>`), open its `index.html` over `file://`, assert the summary lists S1 to S3, open S1, click a claim citation and see the cited value, open the review, and check the plan graph has one rendered node per plan node **and one rendered edge per plan edge** (`.react-flow__edge` count; TASK-24's review found edges silently missing in a real browser while unit tests passed). `pnpm e2e` is a separate step: not part of `pnpm test` or `uv run pytest`, because it needs a browser download. Document it in the UI README. Allowed extra files: `packages/lensgraph-ui/{package.json,pnpm-lock.yaml,playwright.config.ts,tests/e2e/**,README.md}`.

**M3 demo gate (for the human):** run `uv run lensgraph run packages/lensgraph/tests/toy/toy_run.yaml --path packages/lensgraph/tests` and paste its output (run id, report path) into the final summary. The human opens `index.html` from disk (no server) and drills from a claim to its cited data, and views the plan graph.

**Notes from the TASK-18 review:**
- **How the brief reaches the reviewer:** `RunConfig.brief` is run-level, but the reviewer takes it as a node param (so it is in the memo key). When the config has a brief and a reviewer, `arun` sets `nodes[review].brief` from it, unless the config already sets that param explicitly (then raise ParamsError if they differ). Test: changing `brief` in YAML reruns only the review.
- **Import cycle:** `config.py` imports `RunSpec` from `run.py`. Don't import `config` at module level in `run.py`; accept `RunSpec` (RunConfig is a subclass) and read the extra fields with `getattr`/`isinstance` under `TYPE_CHECKING`, or move the RunConfig-specific wiring into `cli.py`.

Out of scope: campaigns (M7), as-of runs (M8), a web frontend.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 lensgraph run <yaml> runs the toy panel with reviewer and writes the report; rerun is all cache hits
- [ ] #2 --invalidate, --no-cache and --profile override the config; config errors exit 2 without a traceback
- [ ] #3 lensgraph report rebuilds a report from the index and blobs alone
- [ ] #4 M3 demo gate output recorded
- [ ] #5 Playwright smoke test opens the generated report from file:// and drills from a claim to its cited value
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
