# Overview

## Intent

Build a **guard-railed assessment framework**. A panel of *lenses* (expert views) each
assess a set of *candidates*, and every candidate gets a structured *dossier*: one verdict
per lens plus an overall stance, with every claim traceable to the data behind it.

The idea came from an LLM "AI hedge fund" (ai-hedge-fund → alpha-capture). The
author's insight is that the pattern is not finance-specific. In synthetic biology,
candidate strains need assessing from biotech, process-engineering, biochemistry and
toxicity points of view. That is the same shape: candidates × lenses → dossiers.

So the work is split into:

- **`lensgraph`**, a domain-agnostic core library. It holds no finance imports and could
  be extracted to its own repo/package later.
- **`alpha_nodes`**, the finance domain built on it. Its first use is **equity universe
  construction**: deciding which tickers belong in a universe, and why. Filtering,
  ranking and portfolio optimisation come later, downstream.

### What "guard-railed" means (agreed)

- **Numbers only come from deterministic calculation nodes.** AI nodes interpret numbers
  and context. They never produce a metric or score that feeds a calculation. An AI lens's
  ordinal *stance* and *conviction* are judgements, not metrics. Aggregators and campaign
  acceptance policies may combine them, which is the point of verdicts. Calc nodes and
  deterministic lenses may not consume them.
- **AI output must pass a schema check** and a **citation check**: every claim cites input
  ids that were actually supplied to that AI node.
- On failure the system **retries with the validation error, then fails loudly**. It never
  substitutes a placeholder (alpha-capture's "50% confidence" fallback is the anti-pattern).

## Goals

1. A per-candidate dossier: a verdict from every lens (status, stance, conviction,
   coverage, claims with citations, flags) plus a deterministic overall stance.
2. Node types with explicit I/O contracts: fetch, transform (ETL), calc, AI lens,
   deterministic lens, aggregator. A broken contract fails that node, and dependents are skipped.
3. **Caching is central.** Source data is expensive, slow and flaky. Code edits must never
   trigger re-downloads, and re-runs only recompute what changed.
4. **Point-in-time (as-of) runs** for backtesting the *deterministic* lenses, with no lookahead.
5. Easy run specification. Small tweaks (thresholds, required columns, model, provider)
   go in a run config file. Structural changes (add a lens, rewire deps, swap a node)
   go in Python.
6. Easy data-provider switching: one adapter per provider, a canonical schema per dataset,
   provider chosen per dataset in config.
7. Universe **campaigns**: repeated, stratified, adaptive sampling until quotas are met,
   with staged evaluation (cheap lenses reject early) and an honest shortfall report.
8. A static **HTML report per run**, where a reader can drill from a claim to the stored
   node outputs behind it (e.g. the prices that fed a momentum calc).
9. Ready to move to cloud later: storage and execution sit behind interfaces.

## Non-goals (for now)

- Portfolio optimisation, cross-candidate ranking, allocation.
- Backtesting AI lenses. LLMs already know how the past turned out, so results would be
  inflated. In as-of runs AI lenses are disabled or marked not backtest-valid.
- Authoring lenses or graphs by non-programmers (YAML-composed graphs). Keep stable node
  names so this can be added later. Do not build it now.
- A web frontend/API (later). The artifact store must be designed so a frontend can sit on it.
- Cloud deployment, distributed execution, scheduling.
- OpenBB, Ray, LangGraph.
- Survivorship-bias-free historical universes (needs a paid delisted-securities source).
  This is a documented limitation.

## Anti-goals (failure even if it "works")

- Silent fallbacks: placeholder verdicts, swallowed exceptions, "empty" that hides "error".
- An LLM inventing numbers that then get used as scores.
- Dossiers that hide missing pieces. Coverage and failures must be visible.
- Lookahead in as-of runs.
- Re-downloading source data because downstream code changed.
- Finance concepts leaking into `lensgraph`.
- A lens reading another lens's verdict. Lenses share data/calc nodes; only aggregators
  and campaign policies read verdicts.

## Constraints

- Python 3.13, `uv` (workspace), pytest with functions and fixtures (no test classes),
  `conftest.py` where useful. Test-driven development. DRY and modular. The author uses VSCode.
- No network in tests. Fake providers; pydantic-ai `TestModel` / `FunctionModel` for LLMs.
- Scale v1: about 100 candidates × 3 lenses, ad hoc on a laptop. About 500 node evaluations
  per lens layer, dominated by HTTP/LLM latency, not CPU.
- Project planning in Linear.

## Approaches considered

The engine question was: what executes the graph? A spike built the same scenario
three ways (see [lessons.md](lessons.md#engine-comparison-spike)). The scenario was a shared
fetch, per-candidate fetch → ETL contract → calc → deterministic lens + AI lens →
dossier, with a contract failure, absent data, an AI retry, disk memoization and config tweaks.

| | Own thin core (asyncio + pydantic) | Apache Hamilton | pydantic-graph `GraphBuilder` |
|---|---|---|---|
| Deps | consumer-declared on node classes | function parameter names | producer→consumer edges + explicit joins |
| Failure-as-data | first-class | had to subclass cache internals; `GracefulErrorAdapter` can't combine with caching | hand-rolled result wrapper |
| Async (LLM concurrency) | native | async driver can't combine with caching | native |
| Memoization | ~60 lines, built | built-in, good | hand-built (174 lines plumbing) |
| Footguns | — | `Parallelizable` + failure sentinel crashed | default join scope silently merges across all candidates |
| Plumbing owned | ~340 lines | ~45 lines (but on internals) | ~175 lines + 68 wiring |

Also ruled out without a spike:
- **Ray**: heavy for I/O-bound work, and it caused real pain in alpha-capture.
- **Dagster/Prefect as the foundation**: heavy for ad hoc laptop runs, and the domain model
  would bend to theirs. They are possible later *executors*.
- **LangGraph**: built for agent loops, not dataflow.

**Chosen: own thin core.** asyncio behind a small `Executor` interface, so another backend
(Prefect, Dagster, pydantic-graph) can be added later without touching node code.
**pydantic-ai** is used for AI nodes (typed output, `ModelRetry` validation loop,
provider-agnostic, test models). The spike's `custom/core` is a *reference*, not a starting point.

## Decision log

| # | Decision | By |
|---|---|---|
| D1 | Generic core is specifically a candidates × lenses → dossier framework, not a general pipeline tool | user |
| D2 | Output is a verdict per candidate. Selection/optimisation is downstream | user |
| D3 | Guard rails as defined above (numbers from calc nodes; schema + citation checks; fail loudly) | user |
| D4 | Verdict schema: status / ordinal stance / conviction / coverage / score / claims / flags / provenance (see core.md) | Claude, accepted by user |
| D5 | Flags are carried, not enforced. Aggregation policy is a pluggable node | user |
| D6 | Graph defined in Python. Small config file for tweaks. No expert-facing DSL yet | user |
| D7 | Failure taxonomy: global → abort; contract → fail + skip dependents; absent → abstain/lower coverage; AI invalid → retry then fail | Claude, user didn't object |
| D8 | Two cache layers: point-in-time source store + content-addressed node memoization. Code edits never refetch | user (central), design by Claude |
| D9 | As-of runs required for deterministic lenses; AI backtesting out of scope | user |
| D10 | HTML report per run now; frontend later; all node outputs stored and addressable for drill-down | user |
| D11 | Own thin core on asyncio; pydantic-ai for AI nodes; executor swappable (after spike) | user, after spike |
| D12 | No OpenBB. Provider adapters + canonical dataset schemas; provider switchable per dataset | user |
| D13 | v1 lenses: price behaviour (deterministic: momentum, trend, risk), quality & value (AI, rubric from Buffett's principles; persona prompt as a switchable variant), price vs fundamentals (AI, divergence-framed) | user + Claude |
| D14 | Universe campaigns with stratified adaptive sampling; staged evaluation allowed (cheap lenses reject early) | user |
| D15 | Names: core `lensgraph`, finance `alpha_nodes`, uv workspace | Claude's call, easy to rename |
| D16 | Storage: DuckDB + Parquet locally, behind interfaces (Postgres/S3 later) | Claude's call |
| D17 | Code-version rule for memo keys: explicit `version` + node class source hash; escape hatch to invalidate from a node | Claude's call |
| D18 | Thin evidence lowers the recommendation: coverage includes data depth; default aggregator is a confidence-weighted, shrunk mean; dossier carries a computed `confidence` | user (principle), formula by Claude |
| D19 | UK/AU fundamentals: free yfinance with depth-aware coverage; paid provider possible later | user |
| D20 | Fetch nodes not memoized (always read the store); price `known_at` = trading date; per-entity provider fallback; USD thresholds via `fx`; backtests in a separate evaluation module | Claude's calls (after builder check) |
| D21 | Data quality: compute ratios ourselves (never ingest Yahoo ratios); units and two currencies explicit; repair-certain/flag-uncertain with per-row records; keep raw responses + `renormalise`; pinned yfinance + canary tickers | Claude, after quirk research; user agreed |
| D22 | Model profiles: `dev` default = Claude Haiku 5.5 at low effort; `local` = Ollama via pydantic-ai; `quality` = Sonnet 5.5; `test` = pydantic-ai test models. Profile is part of memo key + provenance | user (cheapest default, local + API), profile mechanism by Claude |
| D23 | Pydantic-first: all data structures are pydantic models, no dataclasses; nodes are pydantic models whose fields are their params; frames stay pandas + pandera | user (pydantic-first), node-as-model by Claude |

## Repository layout (Claude's call)

```
pyproject.toml            # uv workspace root
packages/
  lensgraph/              # generic core; must not import alpha_nodes
    src/lensgraph/...
    tests/                # includes a toy non-finance domain
  alpha_nodes/            # finance domain
    src/alpha_nodes/{datasets,providers,nodes,lenses,prompts,campaigns}/...
    tests/
runs/                     # run/campaign YAML files
documentation/
spikes/                   # throwaway experiments (not product code)
```

## Left to the builder

- Exact module layout inside each package, beyond what core.md/finance.md fix.
- HTML templating approach (Jinja2 is the obvious default) and chart library.
- DuckDB table layouts, hashing details (e.g. `pd.util.hash_pandas_object` vs Parquet bytes).
- Rate-limiter implementation (e.g. `aiolimiter`) and retry library (e.g. `tenacity`).
- CLI framework (Typer/click) and command names.
- Logging/observability (logfire integrates with pydantic-ai; optional).

## Milestones

These are tracked in `backlog/` (see `backlog/docs/doc-1 - Implementation-plan.md`).

1. Core graph, executor, failure semantics, memoization, blob store + run index. Tested
   on a **toy non-finance domain**, which keeps the core honest about being generic.
2. Verdict/dossier models, deterministic lens base, AI lens with citation guard rail and
   model profiles, confidence-weighted aggregation.
3. Run config (YAML) + CLI, lineage resolution, static HTML report.
4. Point-in-time source store (generic) + finance package, yfinance provider, prices/profile/fx.
5. Price-behaviour lens end-to-end (100 tickers → HTML report).
6. Fundamentals (EDGAR + yfinance) → quality & value lens → price-vs-fundamentals lens.
7. Campaigns (generic) → universe campaign (finance).
8. As-of runs + backtest of the price-behaviour lens.
