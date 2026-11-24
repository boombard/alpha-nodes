---
id: TASK-22
title: M3.6 lensgraph CLI and toy end-to-end report
status: In Review
assignee: []
created_date: '2026-11-23T23:51:15Z'
updated_date: '2026-11-24T08:16:41Z'
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
# cli.py (click; changed from argparse 2026-11-24 at the human's request)
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
- [ ] Write the failing tests (use `click.testing.CliRunner` with `tmp_path` stores; no subprocess needed):
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_bf67e82883d5, worktree task-22
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_bf67e82883d5, branch boom/task-22, 1 commit 238418e): click CLI (lensgraph run CONFIG [--store --invalidate --no-cache --profile --no-report --path], lensgraph report RUN_ID [--store --out]; exit 0/2/3), RunSpec.profile_override, the brief wired from RunConfig into the review node param, local model via Settings, a report written as the React app plus run.json and data/run.js, Playwright e2e (tests/e2e/report.spec.ts on a CLI-generated toy report over file://), core.md and README updated. ACs 1-5 met (test_cli.py: run_toy_writes_report, rerun_all_cache_hits, invalidate_and_no_cache, profile_override, config_error_exit_2, report_rebuilds, local_model_via_settings, brief change reruns only the review, abort exit 3; e2e report.spec.ts).
Coordinator verification: pytest 330 passed, ruff clean, pyright 0 errors, pnpm test 49 passed, typecheck clean, pnpm e2e 1 passed (run myself). Ran the CLI on toy_run.yaml: exit 0, run id, store and report printed; all three candidates have reviews (the brief reached the reviewer); a rerun gives 14 cache hits (every memoizable node except S3's failed and recovered ones) and 0 LLM calls; a YAML typo ('panle') gives exit 2 with 'Error: invalid config: panle: Extra inputs are not permitted' and no traceback. No fix round needed.
Rulings: --profile beats an explicit profile in the config (CLI flags override config); a test2 profile was added to the toy registry; the UI fixture was regenerated (the config gained profile_override) and BUILD_INFO rebuilt (index.html unchanged); click and @playwright/test added; the Playwright outputDir is under node_modules/.cache; only LENSGRAPH_LOCAL_MODEL is read via Settings (other env: profile vars still use os.environ); 'lensgraph report' takes max_rows from the stored run config.

M3 DEMO GATE
Worker: uv run lensgraph run packages/lensgraph/tests/toy/toy_run.yaml --path packages/lensgraph/tests gave run id 20261124T081543-7c1e2c and report .lensgraph/reports/20261124T081543-7c1e2c/index.html (in the task-22 worktree).
Coordinator rerun: run id 20261124T081625-a8f8a1, exit 0, report index.html written; the Playwright e2e drills from S1's claim to its cited value, opens the review, and counts graph nodes and edges in a real browser.
<!-- SECTION:FINAL_SUMMARY:END -->
