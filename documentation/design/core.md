# `lensgraph`: the core library

Domain-agnostic. It must not import anything from `alpha_nodes`. The test suite includes a
toy non-finance domain (e.g. "strains" with fake assay data) to prove it.

## Vocabulary

| Term | Meaning |
|---|---|
| **Candidate** | The thing being assessed (a ticker, a strain). Has an id plus arbitrary attributes (`CandidateRef(id, attrs)`). |
| **Node** | A unit of work with declared inputs, params, output contract, scope. |
| **Lens** | A node that produces a `LensVerdict`. Deterministic or AI. |
| **Panel** | The set of lenses for a run. The graph is everything they transitively need. |
| **Dossier** | Per-candidate output: all lens verdicts + aggregate. |
| **Run** | One execution of a panel over a set of candidates with a run config. |
| **Campaign** | A loop that repeatedly samples candidates and runs the panel until quotas are met. |

## Pydantic-first (user decision)

- **Every data structure is a pydantic `BaseModel`**: configs, node params, node outputs
  (other than frames), verdicts, dossiers, store records, provenance, campaign state.
  **No `@dataclass`, `TypedDict` or `NamedTuple`** for project data.
  - Default `model_config = ConfigDict(extra="forbid")`.
  - `frozen=True` for values that get hashed or cached (outputs, verdicts, params).
- **Nodes are pydantic models too.** A node's *params are its fields*:
  `class Momentum(CalcNode): lookback_days: int = 252; skip_days: int = 21`.
  - Graph building instantiates each node from run config
    (`Momentum.model_validate(cfg.nodes.get("momentum", {}))`), so typos and bad types
    fail at load time.
  - The memo key hashes the node's params field by field through `content_hash`, with sets sorted, so the key is stable across processes.
  - Structural metadata (`name`, `inputs`, `scope`, `version`, …) are `ClassVar`s.
- **Dataframes stay pandas**, validated by pandera `DataFrameModel` schemas (pydantic-style
  declarations, usable as pydantic field types). Row-wise pydantic models for time series
  would be slow and pointless.
- **Environment/secrets** (API keys, SEC User-Agent, store paths, default model profile)
  come via `pydantic-settings`.

## Nodes

Class-based (pydantic models, see above). Each node declares, as `ClassVar`s (cf. spike
`custom/core/node.py`, which used plain class attributes):

- `name`: stable, unique. Used in config, cache keys, citations, reports.
- `inputs`: `{kwarg: upstream_node_name}`. Consumer-declared dependencies.
- `optional_inputs`: same, but an absent/failed upstream gives `None`/`Absent` instead of skipping.
- params: the node's own pydantic fields (see above). They are part of the memo key.
- `output`: the output contract. One of: a pydantic model, a pandera `DataFrameModel`,
  or a plain type. It is **validated after `run`**. A violation fails the node.
- `scope`: `"shared"` (once per run, e.g. a market index) or `"candidate"` (once per candidate).
- `version`: explicit string, bumped by hand when behaviour changes in code the source
  hash can't see (helpers).
- `resource`: optional name of a rate-limited resource (e.g. `"yfinance"`, `"llm:anthropic"`).
- `run(candidate, **inputs, **params)`: sync or async. Sync runs in a worker thread.

Hierarchy (each level adds behaviour, not just a label):

```
Node
├── FetchNode        I/O via a provider; memo key excludes source hash; never cache errors
├── TransformNode    ETL; typically input/output contracts (pandera)
├── CalcNode         pure, deterministic metric(s)
├── LensNode         returns LensVerdict; converts upstream failure into status="failed"
│   ├── DeterministicLens  scored components + thresholds → stance; optional LLM-free claims
│   └── AINode             pydantic-ai agent; citation guard rail; retry policy
└── Aggregator       reads LensVerdicts → Dossier (pluggable policy)
```

Rules:
- Lenses may depend on fetch/transform/calc nodes, **never on another lens**. This is
  enforced at graph build time.
- Only `Aggregator`s and campaign policies read verdicts.

### Contracts

- Input contracts are the upstream node's output contract. A node may also declare
  `input_checks` (e.g. "requires columns X, Y") for requirements stricter than the
  producer's contract. That is how "make small changes to required columns" happens
  without touching the producer.
- Column requirements and thresholds should be **params** where you expect to tweak them,
  so they live in run config.

## Graph

- Built in Python: `Panel([PriceBehaviour, QualityValue, ...])` resolves transitive deps
  from a **node registry** (by `name`). Adding a lens means listing it; its inputs pull in
  their own deps.
- Structural changes go in Python: `panel.replace("raw_prices", MyOtherFetch)`, or by
  registering a different implementation under the same name for a run.
- Validation at build time:
  - no cycles
  - every input resolves
  - no lens→lens edges
  - a shared-scope node cannot depend on candidate-scope nodes
  - params referenced exist in config
- **Partial execution**: `run(targets=[node names], candidates=[...])` computes only the
  required subgraph. This is used for staged campaigns and for "just rerun this lens".
- Rendering: emit a Mermaid diagram of the resolved graph (cheap, useful in reports/docs).

## Execution

- `Executor` interface: `async run(plan) -> RunResult`. v1 implementation: asyncio
  `TaskGroup`. Each node instance awaits its dependencies' futures.
- Per-resource limiters (concurrency + rate) are configured in run config, e.g.
  `yfinance: {concurrency: 4, per_second: 2}`, `llm:anthropic: {concurrency: 8}`.
- Sync node bodies run via `asyncio.to_thread`.
- Node code must not assume a local process: no module globals as caches, no hard-coded
  local paths. Everything goes through the stores passed in context. This keeps a future
  distributed executor possible.

## Failure semantics

| Situation | Mechanism | Effect |
|---|---|---|
| Global failure (provider down, auth invalid) | provider raises `GlobalFailure` after its retries | **abort the run**; partial artifacts kept |
| Node raises / output contract violated | executor catches → `Failed(node, candidate, error)` | node failed; dependents **skipped** (not run) |
| Upstream failed, node is a `LensNode` | default `on_upstream_failure` | `LensVerdict(status="failed", error="upstream 'prices' failed: …")` |
| Optional input failed or absent | passed as `None`/`Absent` | node runs; lens lowers `coverage` or abstains |
| Legitimately empty data (no news) | fetch returns explicit empty result, *not* an error | downstream sees empty; coverage reflects it |
| AI output invalid (schema/citation) | pydantic-ai `ModelRetry` with the error, up to `max_retries` | then node fails. **Never a placeholder** |

- A dossier is always produced per candidate unless the run aborts.
- Failures are recorded in the artifact store. **Failures are not memoized** by default:
  rerunning retries them.
- A node can override `on_upstream_failure` to recover deliberately (rare).

## Memoization (layer 2 cache)

- Key: `hash(node.name, node.version, node source hash, params values, input content hashes, candidate id if candidate-scope)`.
- **FetchNodes are not memoized. They always execute against the source store** (Claude's
  call). That is a cheap local read. The store alone decides whether the network is needed
  (coverage + per-dataset TTL). The fetch node's *output hash* is the hash of the slice it
  returned, and downstream memo keys use that. Consequences:
  - Editing ETL/calc/lens code never refetches. Fetch code isn't in anyone's key; only the
    returned data is.
  - New data arriving (TTL expiry) changes the output hash and correctly invalidates
    downstream. Unchanged data gives early cutoff.
  - The requested range end is `as_of` (or "today" in live runs). It is part of the store
    query, not a memo key.
- Content-addressed blobs: an unchanged output stops the rerun cascade ("early cutoff";
  observed in all three spike implementations).
- Code-version rule (Claude's call): explicit `version` + the node class's source hash.
  The hash doesn't see helper functions, so there is an escape hatch:
  `--invalidate <node>` (that node and descendants) and `--no-cache`.
- AI nodes: the key includes model id, prompt template hash, prompt variant, and the
  rendered context hash. Identical calls are never paid for twice.

## Verdicts and dossiers

```python
class Claim(BaseModel):
    text: str
    direction: Literal[1, -1]          # supports / undermines a positive stance
    cites: list[str]                   # citable ids (see below), must be non-empty

class Flag(BaseModel):
    severity: Literal["info", "warn", "veto"]
    code: str                          # machine-readable, e.g. "price_fundamental_divergence"
    text: str
    cites: list[str] = []

class LensVerdict(BaseModel):
    lens: str
    status: Literal["ok", "abstained", "failed"]
    stance: Literal[-2, -1, 0, 1, 2] | None        # domain supplies labels
    conviction: Literal["low", "medium", "high"] | None
    coverage: float                                # computed by framework, never by LLM
    score: float | None                            # deterministic lenses only
    components: dict[str, float] = {}              # deterministic sub-scores
    claims: list[Claim]
    flags: list[Flag]
    error: str | None
    provenance: Provenance                         # model, prompt hash/variant, input hashes,
                                                   # attempts, tokens/cost, as_of, backtest_valid

class Dossier(BaseModel):
    candidate: CandidateRef
    run_id: str
    verdicts: list[LensVerdict]
    overall_stance: float | None                   # from the aggregator policy
    confidence: float | None                       # computed evidence weight in [0, 1)
    weights: dict[str, float]                      # lens -> effective weight used
    agreement: float | None                        # dispersion of ok stances
    coverage: dict[str, str]                       # lens -> status
    flags: list[Flag]                              # union, for convenience
    summary: str | None                            # optional AI summary citing verdicts only
```

Principles:
- "abstained" ≠ "neutral stance 0".
- No 0–100 confidence from LLMs. Use 3-level conviction, plus the framework-computed coverage.
- The domain layer supplies stance labels (bearish…bullish; reject…advance).
- **Coverage** is computed by the framework as the mean over declared inputs of input
  sufficiency ∈ [0, 1] (a lens may weight inputs differently):
  - absent or empty → 0
  - present → 1, unless the input declares a **depth requirement**
    (`desired_periods`, `desired_history_days`, `desired_items`). Then sufficiency =
    min(1, available / desired), floored by `min_periods` (below which the input counts as absent).
  - Example: quality_value wants 8 annual periods; a UK stock with 4 from yfinance gives
    0.5 for that input.

  The depth actually available is also rendered into AI prompts ("4 of 8 desired years
  available"), so the model's conviction can reflect it.
- **Lens weight** (per verdict, computed, shown in the dossier):
  `weight = lens_weight(config) × coverage × conviction_factor`, with conviction factors
  low/medium/high = 0.5 / 0.75 / 1.0 by default (params). Abstained/failed lenses have weight 0.
- **Aggregation** is a pluggable `Aggregator`. Default policy is a **confidence-weighted,
  shrunk mean**:
  `overall_stance = Σ wᵢ·stanceᵢ / (Σ wᵢ + k)` and `confidence = Σ wᵢ / (Σ wᵢ + k)`,
  where `k` (prior strength, param) pulls thin evidence toward neutral.
  - A candidate whose lenses all ran on thin data gets a stance closer to 0 and a low
    confidence, so it is less likely to clear an acceptance floor. That is the intended
    effect: thin evidence weakens the recommendation rather than being hidden.
  - Agreement = weighted std dev of ok stances. Flags are unioned. Veto handling is
    policy, e.g. a `VetoAggregator`.
  - `confidence` is always computed, never LLM-reported. Acceptance policies may also
    require a minimum confidence.
- Stances are stored as data (not prose), so later analysis can score lenses against outcomes.

## AI nodes (guard rails)

- `AINode` subclasses declare: inputs (as for any node), `prompt` (template file
  path), `variants` (optional named alternative prompts), `max_retries`. The model
  comes from a **model profile** (below), overridable per lens in run config.

### Model profiles (user decision: cheapest by default; local and API both supported)

A named profile resolves to a pydantic-ai model string plus model settings. Profiles live
in config and are selected per run (`llm_profile: dev`) or per lens.

| Profile | Model | Settings | Use |
|---|---|---|---|
| `dev` (**default**) | `anthropic:claude-haiku-5-5` | `thinking: "low"` (pydantic-ai's unified effort setting) | day-to-day runs and iteration; ~20× cheaper than Sonnet 5.5 ($0.10 / $0.50 per MTok) |
| `local` | `ollama:<model>` (pydantic-ai `OllamaProvider`, local OpenAI-compatible endpoint; base URL from settings) | output mode may need `PromptedOutput`/`NativeOutput` if the local model's tool calling is weak | offline / zero-cost runs |
| `quality` | `anthropic:claude-sonnet-5-5` (or stronger) | effort per lens | runs you intend to rely on |
| `test` | pydantic-ai `TestModel` / `FunctionModel` | none | **all automated tests**. Never a real model |

- The profile's resolved model id, settings and output mode are part of the AI node's
  memo key and provenance. A `dev` verdict is never served from cache to a `quality` run.
  Reports show the model per verdict.
- Small and local models will fail the citation and schema checks more often. That's
  intended: the retry-then-fail rail makes it visible rather than producing junk.
  Per-profile `max_retries` is configurable.
- Dossiers from different profiles shouldn't be mixed when comparing runs. The run records its profile(s).
- **Context assembly**: every input is rendered into the prompt under a **citable id**:
  - node-level (`momentum`, `fundamentals`)
  - item-level for collections (`news[<item id>]`)
  - field-level for calc outputs that expose named fields (`quality_metrics.roe_5y_mean`)

  The set of citable ids is computed by the framework, not the prompt author.
- The LLM-facing output schema is a **subset** of `LensVerdict`: stance, conviction,
  claims, flags. The framework fills lens, status, coverage, score, provenance.
- Output validators, which raise `ModelRetry` with a precise message:
  - every claim has ≥1 cite
  - every cite is in the citable set
  - flags use known codes (if the lens declares a code list)
- Static content (rubric, instructions) goes first in the prompt so provider prompt caching
  applies across candidates.
- **Variants** let you A/B prompts via config (e.g. `quality_value: {variant: buffett_persona}`).
  The variant is part of the memo key and the provenance.
- In as-of runs, AI nodes are skipped by default (`ai_in_backtests: false`). If enabled,
  `provenance.backtest_valid = false`.
- Token usage and cost are recorded per call, and are aggregable per run and per campaign.

## Deterministic lenses

- Built from named **scored components**: `Component(name, calc input, scorer, weight)`.
  This is the good idea kept from alpha-capture's `AnalysisStep`.
- Score = weighted combination. Stance comes from configurable thresholds (params).
- Conviction comes from the distance of the score to the nearest threshold (configurable).
- Claims are generated from templates per component, citing the calc fields used.

### Possible future: fuzzy rule bases (not decided)

Recorded 2026-11-23 after a research pass; see TASK-16 for the related aggregation work.

- **What we'd already have isn't really fuzzy logic.** Smoothing stance thresholds with
  overlapping triangular memberships whose degrees sum to 1, and taking the weighted average,
  is a one-input, zero-order Takagi-Sugeno system. Its arithmetic collapses to piecewise-linear
  interpolation between threshold centres (`numpy.interp`). If we adopt it, call it
  "interpolated thresholds"; it needs no fuzzy library or vocabulary.
- **Where real fuzzy logic could earn its place:** combining components *inside* a
  deterministic lens when they interact, which a weighted sum can't express. Example:
  ```
  IF margin_trend is falling AND leverage is high THEN stance is very negative
  IF margin_trend is falling AND leverage is low  THEN stance is mildly negative
  ```
  This means "leverage only matters when margins are falling". Domains where experts can
  state such rules are the likeliest first users; the strain domain is a better candidate
  than finance.
- **Not as the cross-lens aggregator.** Membership degrees aren't probabilities, there is no
  standard treatment of missing inputs, and rule bases grow combinatorially with the number
  of lenses. Coverage, abstention and conflict are better handled by the aggregation work in
  TASK-16.
- **Costs and evidence.** Rule bases and membership shapes are hand-tuned, which adds
  arbitrary parameters. We found no out-of-sample evidence that fuzzy MCDM or fuzzy inference
  beats simple baselines for stock rating; most papers validate by rank correlation or on demo
  data. Hüllermeier's critique ("From knowledge-based to data-driven modeling of fuzzy
  rule-based systems", arXiv 1712.00646) covers rule explosion and tuning.
- **If tried:** keep it inside one deterministic lens behind its `assess`, so the verdict
  contract doesn't change. Use `simpful` (AFL licence; Mamdani and Sugeno), not `pyFUME`
  (reported GPL-3.0). Compare it against the weighted-sum version of the same lens on
  historical data before keeping it, and property-test monotonicity where the rules imply it.

## Run configuration

- A pydantic `RunConfig` loaded from YAML (`runs/<name>.yaml`). It contains:
  - candidates (list), or a campaign spec
  - panel (lens names, in Python registry)
  - per-node params (`nodes.price_behaviour.thresholds: …`, `nodes.prices.required_columns: …`)
  - `providers` per dataset (domain-defined)
  - model per AI lens and prompt variant
  - resource limits
  - `as_of` (optional)
  - cache flags
- Unknown keys are an error (no silent typos).
- The resolved config (after defaults) is stored with the run.

## Source store (layer 1 cache): generic mechanics

The point-in-time store for fetched data. It is shared across runs and keyed by data
identity, never by code. The core provides the mechanics. Domains define datasets and providers.

- **Dataset**: a name + canonical schema + key columns + a *coverage axis* (a date, a
  period, or none for snapshot data) + a TTL policy.
- **Provider**: an adapter that fetches a dataset slice and maps it to the canonical
  schema. It classifies outcomes as `ok`, `empty` (legitimately nothing), `error`
  (transient → retry/backoff, never cached), or `GlobalFailure`.
- **Facts are append-only.** Each row carries `provider`, `fetch_id`, `first_seen_at`, and
  `known_at`: the provider-reported publication time (e.g. filing date) when available,
  else `first_seen_at`. Re-fetches that change a value add a new version (restatements are kept).
- **Coverage = interval sets** per (entity, dataset, provider, params). It records the
  *requested* ranges that were successfully fetched, not the returned dates, so
  weekends/holidays are not "gaps". Gap-fill fetches only the missing intervals, including
  holes in the middle.
- **Fetch-attempt log**: every attempt with outcome and timestamp. `empty` outcomes are
  cached with their own (shorter) TTL, so a delisted entity isn't re-requested every run.
  Errors are not cached.
- **TTL per dataset** (e.g. prices 1 day, fundamentals ~1 quarter, profiles 90 days).
  Freshness is checked *per requested interval*, not as a global "fetched recently" gate.
- **As-of queries**: `query(dataset, entity, range, as_of)` returns the latest version of
  each key with `known_at <= as_of`. Datasets whose provider can't supply real publication
  times are marked `pit_reliable = false`. As-of runs warn, or refuse via config, when a
  deterministic lens depends on them.
- **Offline mode**: no fetching at all. Serve from the store or fail. Used in tests and
  for reproducible reruns.
- **Raw layer, then canonical layer.** Every provider response is kept verbatim and
  immutable (`raw_responses`: provider, request, payload blob, fetched_at, library version).
  Canonical facts are *derived* from raw by the adapter's `normalise()`, stamped with a
  `normaliser_version`.
  - When a new quirk is discovered and the adapter is fixed, `renormalise(dataset,
    provider)` rebuilds canonical facts from stored raw responses. **No re-download.**
  - This is the answer to "the data had to be corrected later".
- **Repairs and checks** run inside normalisation, declared per dataset/provider:
  - **Repairs**: deterministic, known fixes (e.g. pence → pounds, percent → fraction).
    They are applied and recorded per row in a `repairs` column (e.g. `["gbp_minor_unit"]`).
  - **Checks**: invariants that can't be fixed with certainty (e.g. a balance sheet that
    doesn't balance, a 100× day-over-day jump). The value is kept, and the row gets a
    `quality` status (`ok`/`suspect`/`rejected`) with reasons. `rejected` rows are
    excluded from queries by default. `suspect` rows are served, with reasons.
  - Downstream, an input carrying suspect rows lowers that input's sufficiency (and so
    coverage, lens weight and dossier confidence). It also surfaces as a `data_quality`
    warn flag that cites the check. Nothing is silently "fixed" beyond the declared repairs.

## Artifact store and run index

Everything a report or a future frontend needs:

- **Blob store**: content-addressed outputs (Parquet for frames, JSON for models), keyed by hash.
- **Run index** (DuckDB):
  - `runs` (id, config, started/finished, status, totals)
  - `node_results` (run_id, candidate, node, memo_key, output_hash, status, error,
    duration, cache_hit)
  - `verdicts` (flattened LensVerdict per run/candidate/lens)
  - `dossiers`
  - `llm_calls` (tokens, cost, attempts)
  - `campaigns` / `campaign_draws`
- Any citable id resolves to a stored output: `(run_id, candidate, node[, field/item])` → blob.
  That is the drill-down path for "show me the prices behind this claim".
- Interfaces `BlobStore` and `RunIndex`. The blob store is a single fsspec-backed
  implementation (`FsspecBlobStore`) selected by URL: `file://` locally (`FileBlobStore`),
  `memory://` in tests (`InMemoryBlobStore`), `s3://` with `s3fs` installed. Encoding is
  the same everywhere (Parquet, JSON envelopes, no pickle). The run index is DuckDB;
  Postgres is later. The memo cache *is* the blob store plus an index lookup by memo_key.

## Reporting

- `lensgraph` provides the generic HTML report builder:
  - run summary
  - per-candidate dossier page
  - verdicts with claims
  - each citation links to a rendered view of the cited output (table, small chart, JSON)
  - flags and failures visible
  - graph diagram
- Output is static and self-contained (one folder per run, openable from disk). Embedded
  data is limited to what's cited plus summaries, so the size stays sane.
- Domains can register renderers for their output types (e.g. a price-series chart).
- Future frontend: a FastAPI over `RunIndex` + `BlobStore`. No extra data model needed.

## Campaigns

A generic outer loop around the per-candidate graph. It is the first "downstream,
cross-candidate" consumer of dossiers.

```python
class CampaignSpec(BaseModel):
    population: str                      # registered Population source name + filters
    strata: str                          # registered stratum key (e.g. "sector")
    quotas: Quotas                       # total target, per-stratum min (and optional max),
                                         # mode: equal | proportional | explicit
    acceptance: str                      # registered policy over a (possibly partial) dossier
    stages: list[Stage]                  # each: target nodes + gate policy (early reject)
    budget: Budget                       # max candidates evaluated, max LLM cost, max wall time
    batch_size: int
    seed: int
```

Loop:
1. Snapshot the population (store the snapshot hash).
2. Until stopped:
   - **allocate** the next batch across strata in deficit, sized by
     deficit ÷ estimated pass rate (Beta prior, updated by observed pass/fail per stratum),
     capped by remaining budget
   - draw seeded samples without replacement
   - run stage 1 targets → gate → survivors to stage 2 → … → acceptance
   - record every draw and decision
3. Stop when quotas are met, the budget is exhausted, or all deficit strata are exhausted.
4. Output: accepted set, all dossiers, per-stratum stats (drawn / rejected at which stage /
   accepted / pass rate), and a **shortfall report**. Quotas are never relaxed silently.
   Optional explicit relaxation policies (e.g. borrow from other strata) are opt-in.

Memoization makes re-running a campaign with changed quotas cheap: previously evaluated
candidates are cache hits.
