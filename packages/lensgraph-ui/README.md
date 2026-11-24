# lensgraph-ui

The run view: one React app that is the end-of-run report and (later) the live view. It reads the
`RunView` contract (`src/types/run-view.ts`, generated from Python) through a `DataSource`
(`src/data/source.ts`) into one store (`src/store.tsx`). Design: `documentation/design/core.md`,
"Reporting: run view (one app, one contract)".

```sh
pnpm install
pnpm test        # vitest (tests/unit/**) against fixtures/toy-run.json
pnpm typecheck   # app, build config and tests
pnpm dev         # serves the app; put a run.json next to it (or a data/run.js)
pnpm e2e         # Playwright smoke test on the CLI-generated toy report (see below)
pnpm bundle      # vite build -> single dist/index.html, copied into
                 # packages/lensgraph/src/lensgraph/view/app/ with BUILD_INFO.json
```

UI: MUI + MUI X DataGrid (community edition, no Pro features), one theme in `src/theme.ts` (light/dark
following `prefers-color-scheme`; status colours are defined there once).

Layout: `src/` is app code only; tests are in `tests/unit/` mirroring `src/` (`setup.ts`, `helpers/`).
`tests/e2e/` is the Playwright smoke test. Tests import app code through the `@` alias (`@/pages/...`).

Pages (hash routing, so it works on file://): the summary with the candidate list (`#/`, the main
navigation: quick search, column filters, sort, preset chips; state in the hash query), the run-level
plan graph (`#/graph`: one node per node name with a status mix; click a node for its candidates), and
candidate pages (`#/candidate/<id>`: Back to list, Previous/Next along the list's order, a collapsible
candidate-level graph). `orderedCandidateIds` (`src/listOrder.ts`) is the single source of the list order.
LLM text is rendered as text only; never use `dangerouslySetInnerHTML` (a test enforces it).

Scale tests use `tests/unit/helpers/scale.ts` (`makeScaleRun(n)`: n synthetic candidates cloned from the toy fixture).

After changing anything in `src/`, `package.json`, the lockfile or the build config,
run `pnpm bundle` and commit the result: `packages/lensgraph/tests/test_view_app.py` fails on a
stale bundle. Python users never need Node.

Domain renderers for cited values register in `src/components/CitedValue.tsx` (`renderers`, by `kind`).

E2E smoke test (`pnpm e2e`, not part of `pnpm test` or `uv run pytest`): `tests/e2e/global-setup.ts` runs
`uv run lensgraph run packages/lensgraph/tests/toy/toy_run.yaml` into a temp store; `report.spec.ts` opens the
resulting `index.html` over `file://` in Chromium, checks the summary (S1 to S3), opens S1, follows a claim citation to
its cited value, checks the review, and checks the plan graph renders one node per plan node name and one edge
per distinct plan edge. It needs a one-time browser download: `pnpm exec playwright install chromium`.
