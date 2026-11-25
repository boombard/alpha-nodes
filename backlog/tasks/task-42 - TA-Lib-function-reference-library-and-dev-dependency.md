---
id: TASK-42
title: TA-Lib function reference library and dev dependency
status: In Review
assignee: []
created_date: '2026-11-25T06:03:29Z'
updated_date: '2026-11-25T06:12:11Z'
labels:
  - finance
  - docs
dependencies: []
references:
  - documentation/design/finance.md
  - https://github.com/TA-Lib/ta-lib/tree/main/website/src/functions
type: feature
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build a local research reference of TA-Lib's technical-analysis functions, so agents choosing or specifying indicators can read formulas, params, defaults and notes without fetching the web. Also add `ta-lib` as a dev dependency, which the M5 calc tests use as a test oracle. Spec: `documentation/design/finance.md` (Technical analysis and TA-Lib).

Source: https://github.com/TA-Lib/ta-lib/tree/main/website/src/functions (248 Markdown pages, BSD-3-Clause). Snapshot the pages **verbatim**, not summarised: the formulas and conventions are the point, and an LLM rewrite could get them subtly wrong. Pin the snapshot to a commit SHA.

## Files
- create `packages/alpha_nodes/scripts/sync_talib_reference.py`: fetches the pages at a given commit (default: current `main` HEAD, resolved to a SHA), writes them, and regenerates the index. Network use is fine here (a maintenance script, like `record_yfinance_fixtures.py`); tests never call it.
- create `documentation/reference/ta-lib/functions/*.md`: the verbatim pages.
- create `documentation/reference/ta-lib/README.md`: source URL, commit SHA, fetch date, the BSD-3 licence notice, how to refresh, and the index.
- modify `pyproject.toml` (root): add `ta-lib==0.8.3.post1` to the `dev` dependency group (it ships wheels with the C library bundled for cp313 on macOS, Linux and Windows).
- modify `documentation/README.md`: point to the reference.
- test `packages/alpha_nodes/tests/test_talib_reference.py`

## Index (in README.md)
One table row per function, grouped by TA-Lib group (overlap studies, momentum, volatility, volume, pattern recognition, math, ...), columns:
- function name, linked to its page
- title
- one-line description (the page's frontmatter `description`, verbatim)
- inputs (e.g. close, or high/low/close)
- params with defaults
- `in ta-lib-python 0.8.3`: yes/no, from `talib.get_functions()` of the pinned wrapper. Pages for functions the wrapper lacks are kept and marked no.
The group should come from the wrapper's `talib.get_function_groups()` where available, or from the page otherwise. Don't invent a group.

## Steps
1. Write the parsing as pure functions (frontmatter, Inputs/Outputs/Parameters sections → pydantic models; index rendering), separate from the fetching.
2. TDD them on two or three small inline page fixtures: `test_parses_frontmatter_and_params`, `test_index_marks_functions_missing_from_wrapper`, `test_index_groups_are_from_wrapper_or_page`.
3. Add `test_dev_talib_matches_numpy_sma`: a sanity check that the dev dependency imports and `talib.SMA` equals a pandas rolling mean on a small series.
4. Run the script once and commit its output.

## Out of scope
- Using TA-Lib in production calcs, or choosing indicators.
- Rendering charts or the reference CSVs (the site builds those; they aren't in the repo).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 documentation/reference/ta-lib/functions holds the verbatim pages and README.md records the source commit SHA and BSD-3 notice
- [ ] #2 The index lists every snapshotted function with group, description, inputs, params and whether ta-lib-python 0.8.3 exposes it
- [ ] #3 ta-lib==0.8.3.post1 is in the root dev group and uv sync installs it with no system library
- [ ] #4 Parser and index tests pass without network; the whole suite is green
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
Worker: dispatch ctx_bfef94df016c, worktree task-42
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: ta-lib==0.8.3.post1 in root dev group; sync_talib_reference.py (pure parse/render + pydantic models, network only in main); 248 verbatim pages at TA-Lib 6435b2a with README (provenance, BSD-3 notice, refresh, index of 246 functions, 237 in wrapper / 9 not); pointer in documentation/README.md. Review: pages spot-checked byte-identical upstream (rsi, alma, adx, cdlhammer); wrapper availability from talib.get_functions/get_function_groups; one round fixed the hard-coded wrapper version (now talib.__version__). pytest 642 passed, ruff and pyright clean. Open points: uv.lock touched outside Files (required); index.md/stability.md prose pages snapshotted but not indexed. Not in wrapper yet: GATOR, MACDV, ALLIGATOR, CE, MAENV, SSF, SHARPE, SKEW, SORTINO.
<!-- SECTION:FINAL_SUMMARY:END -->
