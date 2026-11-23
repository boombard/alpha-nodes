# Lessons

## From alpha-capture (scanned 2026-11-23)

alpha-capture was ~14.5k lines, mid-refactor. 3 agents + portfolio manager were live;
13 personas were archived.

**Keep (good ideas):**
- Declarative agents built from weighted `AnalysisStep`s → our deterministic-lens
  `Component`s.
- The quantitative/qualitative split: deterministic score with LLM-written reasoning,
  vs. an LLM-owned judgement. That split is the origin of the guard-rail principle.
- Registries for fetchers/stores. Typed fetch params. Idempotent upserts.
- Fetch data first, deduplicated per (ticker, dataset), then compute.
- An offline mode that keeps tests network-free.
- Superset matching in the screener cache.

**Don't repeat:**
- **The "graph" wasn't a graph.** There were three fixed layers (data → researchers →
  portfolio), and dependencies were inferred implicitly from analysis steps.
  → Declared, consumer-side deps; any DAG.
- **The LLM fallback was a lie.** Malformed JSON or a validation error produced a default
  `Signal` with 50 confidence. Ollama used `model_construct` (unvalidated).
  → Retry with error, then fail loudly.
- **Coverage was a single min/max date pair per (ticker, table):**
  - The "fetched recently" check ran before gap detection, so a 30-day fetch blocked a
    later 365-day request.
  - Coverage was overwritten rather than unioned, causing repeated refetches.
  - Holes in the middle of a range were invisible.

  → Interval sets per (entity, dataset, provider, params), with freshness per interval.
- **Empty and error looked the same.** `fetch()` swallowed all exceptions and returned
  empty, so delisted or rate-limited tickers were retried every run.
  `InstrumentInfo` failures overwrote good rows with empty ones and blocked refetch for 180 days.
  → Explicit outcome classification and a fetch-attempt log.
- **Point-in-time was a no-op.** yfinance fetchers set `filing_date=None`, and the as-of
  filter let NULLs through, so backtests would leak future fundamentals. Re-fetches
  overwrote restatements.
  → Append-only facts with `known_at`, plus a `pit_reliable` flag per dataset/provider.
- **Provider quirks leaked:**
  - `date.today()` was used as `period_date` for snapshots, so they piled up like periods.
  - News requests silently ignored date ranges.
  - Column aliases crept in despite a "no mapping layer" rule.

  → Mapping lives deliberately in the provider adapter.
- **Ray/OpenBB friction:**
  - OpenBB's `auto_build` lock race crashed concurrent workers.
  - Ray skipped packaging a directory because of a `.gitignore` rule.
  - Stale venvs in workers; DB connection pooling in workers.
  - Neither tool's choice was ever justified in the plans.
- **Universe builder:**
  - The "fetch more until enough" loop was a stub comment.
  - The sector filter was a no-op (sector was fetched after filtering).
  - The pool was the top-500-by-volume per country.
  - There was a `.info` call per candidate.
  - Nothing handled survivorship.
- **Doc drift.** CLAUDE.md/AGENTS.md described modules that didn't exist.
  → Keep `documentation/` small and update it in the same PR as the code.

## From ai-hedge-fund

LangGraph `StateGraph` fan-out: analysts → risk manager → portfolio manager. Function
agents, one file per persona; financialdatasets.ai + diskcache; langchain LLM calls with a
3-attempt loop. Useful as a catalogue of analyst ideas; not as architecture.

## Engine-comparison spike

Code: `spikes/engine-comparison/` (throwaway). Each implementation has a `NOTES.md`.

The scenario was identical across all three:
- a shared index fetch
- per candidate: fetch prices + news → pandera ETL contract → momentum calc →
  deterministic lens + AI lens (pydantic-ai `FunctionModel` whose first answer cites a
  non-existent input) → dossier

The demo had four steps (fresh / identical rerun / config change / code-path change).
All three met the expected behaviour: network calls 7 → 0 → 0 → 0, with correct rerun sets.

| | Own core | Hamilton 1.90 | pydantic-graph 2.71 |
|---|---|---|---|
| Plumbing LOC | 338 | ~45 (subclasses cache adapter) | 174 + 68 wiring |
| Node definition style | classes, `inputs`/`optional_inputs`/`params` | functions, param names | functions + explicit edges/joins |
| Failure-as-data | built in | `GracefulErrorAdapter` and cache adapter both own `do_node_execute`, so they can't be combined. The workaround subclasses cache internals | `Out` wrapper convention |
| Async | native | async driver + cache can't be combined, so `asyncio.run` inside the node | native |
| Fan-out | built in (scope) | one `execute()` per candidate. `Parallelizable` + failures crashed | `map`. Default `preferred_parent_fork='farthest'` silently joins across candidates |
| Notable positive | fits the domain model | tersest nodes; good caching; `@config.when`; `@check_output(importance="fail")` | Mermaid render |

Cross-cutting findings:
- **Early cutoff works**: an unchanged output stops the rerun cascade.
- **Source hashing misses helpers**: both the own core and Hamilton hash only the
  node's own source. Hence the explicit `version` plus `--invalidate`.
- pandera: use `import pandera.pandas as pa`. Plain `import pandera` is deprecated for pandas.
