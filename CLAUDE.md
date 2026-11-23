# alpha-nodes

A guard-railed "panel of lenses" framework: deterministic and AI lenses assess candidates
and produce auditable dossiers. There is a generic core (`lensgraph`) and a finance domain
on top (`alpha_nodes`).

**Read `documentation/README.md` first.** The design lives in `documentation/design/`.
When code changes behaviour described there, update the doc in the same change.

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
- `spikes/` is throwaway reference code. Don't import from it.
