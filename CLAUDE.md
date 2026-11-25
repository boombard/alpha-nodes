# alpha-nodes

A guard-railed "panel of lenses" framework: deterministic and AI lenses assess candidates
and produce auditable dossiers. There is a generic core (`lensgraph`) and a finance domain
on top (`alpha_nodes`).

**Read `documentation/README.md` first.** The design lives in `documentation/design/`.
When code changes behaviour described there, update the doc in the same change.

Work is tracked in `backlog/` (Backlog.md, CLI: `npx -y backlog.md@1.57.4`). The plan overview,
global constraints and review focus are in `backlog/docs/doc-1 - Implementation-plan.md`.
The coordinator/worker workflow is in `documentation/workflow.md`. If you are implementing
a task, follow its Steps and stay inside its Files list.

Code documentation: every module, class and public function or method gets a docstring
that tells a human reader what it is and what it's for. Where its place in the architecture
isn't obvious from the name and module, say where it fits and point to the design section
(e.g. "Memo cache key; see documentation/design/core.md, Memoization"). Document params
and fields whose meaning isn't obvious from name and type. No boilerplate restating the
signature. Tests and test-only helpers need a docstring only when the test name isn't
self-explanatory.

Commands: `uv sync`, `uv run pytest`, `uv run ruff check`, `uv run pyright`.
UI (`packages/lensgraph-ui`, only when changing it): `pnpm -C packages/lensgraph-ui install|test|typecheck|bundle`.

Hard rules (see `documentation/design/overview.md` for why):
- `lensgraph` must never import `alpha_nodes` or contain finance concepts.
- AI nodes never produce numbers used in scoring. Their output must pass schema and
  citation validation, or fail. No placeholder fallbacks.
- Lenses never depend on other lenses' verdicts.
- Tests never hit the network or a real LLM (fake providers; pydantic-ai `TestModel`/`FunctionModel`).
- Pydantic-first: project data structures are pydantic models (frames: pandas + pandera).
  No `@dataclass`, `TypedDict` or `NamedTuple`.
- The default LLM profile is the cheapest (`dev`: Claude Haiku 5.5, low effort). Don't
  change defaults to pricier models.
