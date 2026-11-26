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
  hash can't see and `code_deps` doesn't cover.
- `code_deps`: tuple of helper functions or modules (default empty) whose source
  `code_version()` also hashes, so editing a kernel or helper invalidates the node's cache.
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
| Legitimately empty data (no news this week) | fetch returns `ok` with an empty frame, *not* an error | downstream sees empty; coverage records the range |
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
- Code-version rule (Claude's call): explicit `version` + the source hash of the node class and all its `Node` base classes (so editing a shared lens template or aggregator invalidates subclasses' caches).
  Helpers are covered by `code_deps`: `code_version()` also hashes `inspect.getsource(d)` for each
  declared function or module, in declared order. With `code_deps` empty the hash is unchanged.
  Anything still invisible (undeclared helpers, third-party code) has the escape hatch:
  `--invalidate <node>` (that node and descendants) and `--no-cache`.
- AI nodes: the key includes model id, hash of the rendered system prompt (template plus the glossary
  data dictionary, unless ablated), prompt variant, and the lens's presentation fingerprint (its bound unit map and the renderer source; see Units). Input values enter through their content hashes. Identical calls are never paid for twice.

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
    stance_mean: float | None                      # continuous stance in [-2, 2] that aggregators
                                                   # use; framework-computed (mean of AI samples,
                                                   # or interpolated score); float(stance) by default
    stance_spread: float | None                    # instability of the stance; None = not measured
    coverage: float                                # computed by framework, never by LLM
    score: float | None                            # deterministic lenses only
    components: dict[str, float] = {}              # deterministic sub-scores
    claims: list[Claim]
    flags: list[Flag]
    error: str | None
    provenance: Provenance                         # model, prompt hash/variant, input hashes,
                                                   # attempts, tokens/cost, as_of, backtest_valid,
                                                   # stance_samples (AI lenses: one per sampled run),
                                                   # glossary_terms (AI lenses: entry ids in the prompt)

class Dossier(BaseModel):
    candidate: CandidateRef
    verdicts: list[LensVerdict]
    overall_stance: float | None                   # from the aggregator policy
    direction: float | None                        # plain weighted average of ok stances
    evidence_share: float                          # share of the panel's possible evidence that arrived
    confidence: float                              # computed, in [0, 1]; equals evidence_share; 0.0 if no ok lens
    weights: dict[str, float]                      # lens -> effective weight used
    agreement: float | None                        # dispersion of ok stances
    coverage: dict[str, str]                       # lens -> status
    flags: list[Flag]                              # union, for convenience
```

Principles:
- **No run ids inside node outputs, dossiers included.** Memoized outputs must depend only on
  their inputs. A dossier stamped with `ctx.run_id` would come back from the cache carrying the
  previous run's id, and its content hash would change every run, so downstream nodes (reports)
  would never cache-hit. Run identity lives *around* outputs: the run index (`dossiers` keyed by
  run_id and candidate), `RunResult.run_id`, and at export time a wrapper
  `DossierRecord(run_id, created_at, dossier)` built outside the graph.
- "abstained" ≠ "neutral stance 0".
- **Critical inputs and minimum coverage.** A `LensNode` has two params: `critical_inputs` (a set of
  input names it can't judge without) and `min_coverage` (0..1, default 0). A name not among the
  lens's inputs is rejected at plan time (`ParamsError`, like `weight_overrides`). In `run`, after
  coverage and `input_sufficiency` are computed and *before* `assess`, an unmet threshold gives an
  `abstained` verdict (not `failed`: missing data is a legitimate outcome, and the aggregator gives
  abstentions weight 0). A critical input with sufficiency 0 (absent, empty, or below its depth
  minimum) wins: `critical input '<name>' unavailable` (first in sorted order; more are counted,
  `(+1 more)`). Otherwise coverage below `min_coverage` gives `coverage 0.40 below minimum 0.60`.
  The verdict keeps the computed coverage and `input_sufficiency`, has no stance, conviction or
  claims, and its provenance holds only `lens_version` and `input_hashes`: no model call happened,
  so an AI lens spends nothing. Both params are part of the node's params, so changing them
  changes the memo key. Not built: suspect rows lowering sufficiency.
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
- **Aggregation** is a pluggable `Aggregator`. Default policy is an **evidence-share**
  weighted mean (`ShrunkMeanAggregator`), over ok verdicts with weights `wᵢ` as above:
  - `W_max = Σ lens_weightᵢ × max(conviction_factor)` over *every* panel lens, ok or not:
    the most weight the panel could deliver.
  - `direction = Σ wᵢ·stanceᵢ / Σ wᵢ` (plain weighted average; None if `Σ wᵢ = 0`).
  - `evidence_share = Σ wᵢ / W_max`, and `confidence = evidence_share`.
  - `overall_stance = direction × evidence_share`.
  - Why not a fixed prior `k` (`Σ wᵢ·sᵢ / (Σ wᵢ + k)`)? It biased small panels: two perfect +2
    lenses could never exceed 1.33, so results depended on panel size. The Bayesian k-shrink
    remains a TASK-16 alternative policy.
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
  path), `variants` (optional named alternative prompts), `flag_codes` (optional closed list of
  flag codes). Retries are per profile (`max_retries`). The model
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
  Per-profile `max_retries` is configurable. When retries run out, the node fails and its
  error carries the last rejection (e.g. the unknown citation ids).
- Profiles are `LLMProfile`s held in a `ProfileRegistry` (`services["profiles"]`, default
  `ProfileRegistry()`). The `local` profile reads its model string from the environment
  variable `LENSGRAPH_LOCAL_MODEL`; resolving it when unset raises a `ValueError` naming the
  variable. Tests plug a `FunctionModel` in through `model_overrides`.
- Each profile may carry `usage_limits` (request and token ceilings for one call, retries
  included; defaults `request_limit = max_retries + 2`, plus `total_tokens_limit = 50_000` for
  `dev` and `quality`). Exceeding one raises pydantic-ai's `UsageLimitExceeded`, which fails the
  node like exhausted retries; there is no fallback. The limits are part of the fingerprint.
- One model call per lens run. Repeated sampling (stance mean/spread) is deferred to TASK-17.
- Inputs with nothing to show (an `Absent`, or an empty list) are rendered as
  `NOT AVAILABLE` and are not citable, even though `citable_ids` lists their node-level id.
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
  The variant is part of the memo key and the provenance. An undeclared variant name is a
  `ParamsError` at plan time, never a silent fallback to the default prompt.
- In as-of runs, AI nodes are skipped by default (`ai_in_backtests: false`). If enabled,
  `provenance.backtest_valid = false`.
- Token usage and cost are recorded per call, and are aggregable per run and per campaign.

## Glossary (user decisions, 2026-11-26: mechanism; then always on for AI nodes)

Status: the mechanism landed with TASK-63 (opt-in notes); the always-on data dictionary below
(claims, binding at plan build, ablation-only switch) is implemented by TASK-66.

A domain ships a **glossary**: a directory of Markdown files, one per term, each with YAML
frontmatter. It is the single home of per-term definitions, and it has two readers:

- **Humans**: what a term means, how we compute it, why it matters, where it misleads.
- **AI nodes (always)**: the *data dictionary* of the lens's evidence. Almost every number we
  hand a model is our own version of a metric (its window, basis, sign, units and fallbacks),
  which no model knows from training. So a definition is part of the evidence, not optional
  coaching for weaker models: every field that reaches an AI lens must have an entry, and the
  lens's system prompt carries each entry's short prompt note. The note is interpretive only;
  the model never computes (AI nodes, guard rails).

Design docs keep policy (why a convention was chosen) and link to entries; kernel and field
docstrings point to their entry. Prompt templates keep instructions (what to weigh, how to
judge) and refer to fields by name; what a field *means* lives only in its entry.

**Entry file** `<id>.md` (the file stem is the id, kebab-case):

```yaml
---
id: fcf                       # = file stem
name: Free cash flow
abbreviations: [FCF]
aliases: [free cash flow to equity (loosely)]
kind: money                   # free text, domain-defined (money, ratio, growth, count, date, ...)
fields: [CashGenerationResult.fcf]     # claims: "Model.field" or "Model"; see Claims
implemented_by: [alpha_nodes.nodes.fundamental_calcs._fcf]   # dotted paths; must import
related: [owner-earnings, fcf-conversion]                    # other ids; must exist
status: draft                 # draft (written from model knowledge) | verified (researched)
sources: []                   # required non-empty when status is verified
---
```

Frontmatter also carries `summary` (one human sentence, at most 30 words: the tooltip text) and
`category` (navigation group, domain-defined, e.g. profitability, leverage, valuation, price).

Body sections, in this order (`##` headings; required unless marked optional). Each heading maps
to a fixed section key, which is what code and the browser use; the heading text is display only:
Definition (`definition`) · How we calculate it (`calculation`) · Why it matters (`relevance`) ·
Shortcomings and pitfalls (`shortcomings`) · Provider notes (`provider_notes`, optional) ·
Similar terms (`similar`) · Sources (`sources`, optional while draft) · Prompt note (`prompt_note`).

The **Prompt note** (at most 60 words) says what the number is *in our data*: basis, window,
sign and fallbacks (not units: values arrive formatted with their unit, see Units), plus at most one
interpretive caution. A verbal definition is fine; a formula to apply is not (no `$` math;
a domain's tests may be stricter, e.g. no `=`).

**Claims (fields to entries):**

- An entry's `fields` lists claims. `Model.field` claims one field; `Model` claims every field of
  that model, and is meant for window and metadata models (a price window, a listing profile).
  Never use a whole-model claim on a model with metric fields: a new metric field would be
  covered silently. `Model` is the class `__name__` of a pydantic model or a pandera
  `DataFrameModel` (frame columns are its fields).
- A field resolves by walking its output model's MRO from the model itself up: at the first
  class that declares the field (in its own annotations, not by inheritance), the claim
  `Class.field`, else `Class`, wins; if neither, the next class up. So a field inherited from a
  window base is claimed once, on the base; a subclass claim on an inherited field never
  matches and `unresolved_claims` reports it as stale.
- No claim appears twice (validated on load). `Glossary.term_for(model, field) -> str | None`
  is the resolver. `Glossary.unresolved_claims(models) -> list[str]` lists the claims that name
  no class or field among `models`; a domain test passes every node `output` of its registry
  and asserts `[]`, so a renamed or removed field can't leave a stale claim behind.

**Browser-ready format** (so a glossary page and run-view links can be added later without
reformatting entries):
- Bodies are CommonMark only: no raw HTML (inside code spans it is fine), no templating, no
  images for now.
- Formulas use KaTeX-compatible math: inline `$...$`, display `$$...$$` (readable as plain text in
  an editor; rendered in the browser). Delimiters must balance (validated). A literal dollar sign is written `\$`.
- Links between entries are relative Markdown links, `[owner earnings](owner-earnings.md)`: they
  work in editors and on GitHub, and the browser rewrites `*.md` to its own route. Every link must
  resolve to an entry (validated).
- `Glossary.export() -> GlossaryExport` is the contract for the browser, the same pattern as
  RunView: a pydantic model (`schema_version`, `content_hash`, entries with frontmatter, `summary`,
  and sections as Markdown strings keyed by section key), serialised to `glossary.json`; its TS
  types are generated like RunView's when the UI work happens.
- Field linking needs nothing new: the run-view builder knows each cited output's model, so
  `Glossary.term_for` gives the term id to attach to a field cite.
- Later (not now): a standalone glossary page in the run view app, term links and tooltips on
  cited fields, and `run.json` embedding the subset of entries a run cited (with the
  `content_hash`), so an old report shows the definitions as they were when it ran.

**Data dictionary in AI prompts (lensgraph, domain-free):**

- An `AINode` names its glossary directory: `glossary: ClassVar[Path | None] = None` (None: the
  domain has no glossary and no dictionary is rendered). Nothing is loaded at import, so a broken
  entry cannot break importing a domain's lenses.
- **Binding at plan build.** `build_plan` calls `Node.bind_upstream(outputs)` on every node
  instance, with `{input name: upstream output contract}` taken from the resolved classes
  (replacements included). It is a no-op except on `AINode`, which loads its glossary and
  resolves every field of every input's contract, optional inputs included: pydantic model
  fields, pandera frame columns, and the item model of a `list[Model]` contract. Other
  contracts (a bare `list`, plain types) contribute no fields.
- The contract binding sees is `Node.contract()` (default: `output`); runtime validation still uses `output`.
  A dataset fetch node (`DatasetFetch`, `DatasetFetchMany`) sets `frame_schema` to the dataset's canonical
  columns and that is its contract, so a frame an AI lens reads directly (e.g. a profile) is covered
  column by column; the fact meta columns the slice also carries are not in the dictionary.
- **Strict.** A field with no claim fails the plan with a `GlossaryError` naming the lens, the
  input and the field, before any model call. So does an invalid entry, but only in plans that
  contain an AI lens using that glossary; a price-only run never loads it.
- `glossary_concepts: ClassVar[frozenset[str]] = frozenset()` adds ids for concepts the prompt
  uses that are not fields (e.g. a rubric term); unknown ids fail the plan.
- `Glossary.dictionary_block(paths, concepts) -> str`, where `paths` maps entry id to the
  evidence paths it covers: "## Data dictionary", then one line per entry in id order,
  `- <paths> (<kind>): **<name> (<abbreviations>)**: <prompt note>`, then the concept entries
  without paths. Paths are the exact evidence paths `input.field` (a frame column is
  `input.column`), compacted per input as `input.{a, b}` when one entry covers several fields
  of one input. Deterministic; escaped dollars (`\$`) are unescaped.
- The block is appended to the system prompt after the template's static content. It depends
  only on classes, never on values, so it is static per lens (prompt caching applies) and does
  not change when an input is NOT AVAILABLE for a candidate.
- **Ablation only:** param `use_glossary: bool = True`. False omits the block, set per node in a
  run config (`nodes: {quality_value: {use_glossary: false}}`), to measure what the dictionary is
  worth; coverage is still checked. Model profiles carry nothing about the glossary: changing
  the model must never change what the prompt says.
- **Hashing:** the prompt hash is the hash of the rendered system prompt (template + block). So
  editing a used entry's name, abbreviations, kind or prompt note, or adding a field to an input's
  output model, reruns that lens and nothing else; editing an entry's other sections reruns
  nothing. Provenance records `prompt_hash` and `glossary_terms` (every id in the block, sorted;
  empty when ablated).

**Loading and CLI:**

- `GlossaryEntry` (pydantic: frontmatter fields + `sections`, keyed by the fixed section keys)
  and `Glossary.load(directory) -> Glossary` validate everything above: id = stem, required
  headings present, `related` ids exist, `sources` non-empty for `verified`, no claim made twice,
  prompt note length, no raw HTML, balanced math, resolvable relative links. Every failure is a
  `GlossaryError` naming the file. `implemented_by` resolution is checked by
  `Glossary.check_imports()` (a domain test calls it; loading never imports domain code).
- `lensgraph glossary DIR` lists entries as `status  id  fields`, drafts first, and exits
  non-zero on a validation error.

## Units (user decision, 2026-11-26)

Status: designed; core mechanism TASK-67, run view TASK-68, finance annotations TASK-69.

A number's unit is a property of the **field**, declared once on the output contract, and every
place that shows a number formats it from that declaration: the AI evidence, deterministic claim
text and the run view. Values stay plain floats and ints everywhere they are computed, stored,
hashed and cached (kernels, frames, blobs, the source store, memo keys). There are no quantity
objects (pint was considered and rejected: dimension checking buys little when arithmetic runs in
numpy kernels on plain arrays, and the one mix that matters, currency, is guarded in the domain).

**`Unit`** (`lensgraph.units`): a frozen pydantic model, pure data, so it serialises into
provenance and the run view and needs no domain code to render:

```python
class Unit(BaseModel):                     # frozen, extra="forbid"
    id: str                                # stable label, e.g. "fraction", "money"; shown in headers
    style: Literal["percent", "multiple", "number", "integer", "compact"]
    suffix: str = ""                       # e.g. "/yr", " bars", "/share"
    prefix_field: str | None = None        # sibling field / row column whose value prefixes it (e.g. a currency code)

def format_value(value: float | int | None, unit: Unit, row: Mapping[str, Any] | None = None,
                 *, signed: bool = False) -> str | None
def unit_of(model: type, field: str) -> Unit | None    # pydantic Annotated metadata or pandera Field metadata["unit"]
```

- Generic units ship with the core: `FRACTION` (percent), `FRACTION_PER_YEAR` (percent, "/yr"),
  `MULTIPLE` ("×"), `NUMBER`, `COUNT` (integer), `BARS`, `DAYS`, `YEARS`. A domain defines its own
  as plain `Unit` values (finance: money and per-share money with `prefix_field` naming the
  currency field); the core never names a domain unit.
- **Declaring:** pydantic fields use `Annotated[float | None, FRACTION]`; frame columns use
  `pa.Field(metadata={"unit": FRACTION})`. `unit_of` walks the MRO like glossary claims.
- **Formatting** (one function, the only formatter): 3 significant figures, never scientific
  notation, and a non-zero value never prints as zero (precision grows instead: 0.0004 is
  "0.04%"); `percent` multiplies by 100; `compact` uses k/m/bn/tn; `integer` is exact; `prefix_field`
  prepends the sibling value ("USD 12.3bn"); None stays None (rendered `null`). `signed` adds "+".
- **Strict, at plan build.** `LensNode.bind_upstream` records the unit of every numeric field
  (int or float, not bool) of every input contract; one without a unit fails the plan with a
  `UnitError` naming the lens, the input and the field. AI lenses check every numeric field of
  every input; deterministic lenses check only their component sources (the only fields that
  reach their claims). Non-numeric fields (dates, text, codes) take no unit. A bare scalar output
  contract (e.g. `output = float`) has no field to annotate, so it is not unit-checked and its
  claims format as `NUMBER`; to give such a number a unit, wrap it in a model.
- **AI evidence** (`render_context`): a model field with a unit renders as its formatted string
  (`"roe_mean": "15.3%"`); frame cells of a unit column are formatted, with headers left as the
  column names, since they are citable ids. Prompt notes therefore never restate units (Glossary).
- **Deterministic claims:** `claim_template` is formatted with `name`, `value` (formatted),
  `signed` (formatted, with sign) and `raw` (the float). Default `"{name}: {value}"`.
- **Provenance:** a verdict records `cite_units` (each cited field path, or `input.column` for a
  cited frame, to its `Unit`), so the run view formats cited values from the index and blobs
  alone, with no domain import.
- **Memoization:** a lens's memo salt covers its bound unit map and the source of
  `lensgraph.units` and `lensgraph.context`, so changing a unit or the formatter reruns the lenses
  that show it, and nothing else.

## Deterministic lenses

- Built from named **scored components**: `Component(name, calc input, scorer, weight)`.
  This is the good idea kept from alpha-capture's `AnalysisStep`.
- Score = weighted mean of the scored components present (weights renormalised; a missing,
  `Absent` or non-finite component is skipped; none left means abstain). Stance comes from
  configurable thresholds (params).
- Conviction comes from the distance of the score to the nearest threshold (configurable).
- `stance_mean` is the score interpolated between threshold centres (`numpy.interp`), so it is
  monotone in the score; the integer stance still comes from the thresholds.
- Claims are generated from templates per component, citing the calc fields used; values are
  formatted by the cited field's unit (see Units).
  `Component.evidence` lists extra citable ids (e.g. a chart) appended to the claim's cites,
  each only if it is in `citables`; an unavailable evidence input never fails the claim.
- `scorer_overrides` (param, `{component name: LinearScorer}`) replaces a component's default
  scorer per run, like `weight_overrides`; unknown names are rejected.

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
- Wiring fields of the YAML (`RunConfig`, a `RunSpec` subclass):
  - `registry`: `"module:attr"` of a `NodeRegistry` or a zero-arg factory. `services`: the same for the
    services mapping. Both are imported after `--path` directories are prepended to `sys.path`.
  - `brief`: the run-level `AssessmentBrief`. `arun` copies it into the reviewer's `brief` node param (so it is
    in the memo key and changing it reruns only the review); an explicit, different `nodes.review.brief` is a
    `ParamsError`.
  - `report`: `enabled`, `out_dir` (default `<store>/reports/<run_id>`), `max_rows`.
  - `profile_override`: a model profile forced on every AI node (`AINode` subclasses and the reviewer),
    replacing any `profile` in `nodes` (flags beat the config).
  - `sources`: the source-store wiring (optional). `catalog` is `"module:attr"` of a `SourceCatalog` (a domain's
    `datasets` and `providers`, the latter factories taking a `ProviderContext` of `cache_dir` and `clock`);
    `providers` maps each served dataset to its provider names, primary first; `offline` (default false);
    `limits` overrides a provider's `RateLimitPolicy` by provider name. `arun` builds the DuckDB store at
    `<store>/sources.duckdb` (blobs in the run's blob store), injects it as the `sources` service (a `sources`
    entry already in `services` wins, which tests use) and closes it when the run ends, aborted or not. An
    unknown dataset or provider name is a `ParamsError` naming it.
  - Fetch nodes: `DatasetFetch` (per candidate; entity is the candidate id or `attrs[entity_attr]`; `lookback_days`
    gives the window from that many days before `as_of` (or the store clock's today) through that day, inclusive: N+1 calendar days) and `DatasetFetchMany` (shared scope, a fixed
    entity list, one `ensure` call so provider batching applies) read the slice and return its frame (canonical
    plus fact meta columns). An empty slice is an empty frame; `SourceUnavailable` fails the node and its
    dependents skip. List-valued cells (`repairs`, `quality_reasons`) hash by their canonical JSON, the same
    whether they are lists or the arrays a Parquet round trip gives back.
- The stored run config is the resolved dump: `nodes` includes the brief and the profile override.
  `lensgraph report` relies on it.
- **CLI** (`lensgraph`, click):
  - `lensgraph run CONFIG.yaml [--store PATH] [--invalidate NODE]... [--no-cache] [--profile NAME] [--no-report] [--offline] [--path DIR]...`
  - `--offline` overrides `sources.offline` for the run (an error when the config has no `sources`).
  - `lensgraph sources status [--store PATH] [--dataset NAME] [--suspect]` reads `<store>/sources.duckdb` only (no
    catalog) and prints, per dataset and provider: entities, covered ranges per entity, attempts by kind, and
    suspect and rejected row counts (over all stored versions); `--suspect` also lists each suspect row (entity,
    key columns, reasons). Exit 0; exit 2 if there is no source store.
  - `lensgraph report RUN_ID [--store PATH] [--out DIR]` rebuilds the report from the index and blobs alone.
  - Store root: `--store`, else `LENSGRAPH_STORE_ROOT`, else `.lensgraph`.
  - Prints `run id:`, `store:`, a `nodes:` line (counts by status, zero counts omitted, e.g.
    `nodes: 21 ok, 2 failed, 3 skipped`), one `failed: <node>[<candidate>]: <first line of the error>` line per
    failed node (capped at 20, then `… and N more`; skipped nodes are counted, not listed), and `report:` (a report is `install_app` + `write_run_view`: `index.html`,
    `run.json`, `data/run.js`). An aborted run prints the same status lines (from `RunAborted.result`).
  - Exit codes: 0 ok (failed nodes are data), 2 config or params error (one line on stderr), 3 aborted run
    (the report is still built from what finished).

## Source store (layer 1 cache): generic mechanics

The point-in-time store for fetched data. It is shared across runs and keyed by data
identity, never by code. The core provides the mechanics. Domains define datasets and providers.

- **Dataset**: a name + canonical schema + key columns + a *coverage axis* (a date, a
  period, or none for snapshot data) + a TTL policy.
- **Provider**: an adapter that fetches a dataset slice and maps it to the canonical
  schema. It classifies outcomes as `ok`, `empty`, `error` (transient → retry/backoff,
  never cached), or `GlobalFailure`.
  - **`empty` is entity-level**: the provider has nothing at all for this entity (unknown or
    delisted ticker). A known entity whose requested range simply has no rows (weekend,
    holiday, today before the close, a week without news) is `ok` with an empty frame and
    `settled_through`, so coverage records the range like any other. This is why coverage
    keeps one `empty_at` per (dataset, entity, provider, params), not per interval. While
    a cached `empty` is fresh the store fetches nothing for the entity but still serves any
    facts it already holds (a delisted ticker keeps its history).
  - Providers are swappable (e.g. a free feed now, a paid one later). The core knows a
    provider only through what it **declares**: entities per request (`max_batch`, 1 =
    no batching), a rate-limit policy (max concurrency, requests/s, burst, backoff
    schedule, give-up thresholds), and per dataset whether it is `pit_reliable`.
  - The core does the scheduling: gap-fill produces (entity, interval) work items, groups
    them up to `max_batch`, and runs them through one shared limiter per provider. On a
    rate-limit outcome the whole provider pauses (not just one request). After the
    declared number of consecutive rate-limit episodes or connection failures the
    provider raises `GlobalFailure`. Each work item is persisted as soon as it finishes,
    so a re-run after a stop resumes from the gaps.
  - **Circuit breakers** (both off by default, per provider, counted in completion order over
    *distinct entities*: an entity's retries count once). `RateLimitPolicy.max_consecutive_errors`
    raises `GlobalFailure` (naming provider, streak length and last message) after that many
    entities in a row whose final outcome is `error`, so a systemic failure isn't retried
    entity by entity across the universe. `max_consecutive_empty` does the same for `empty`
    (a provider incident or throttling disguised as "not found"); while an empty streak is open
    its outcomes are withheld from persistence, handed over when a non-empty outcome breaks the
    streak or the run ends below the threshold, and **not cached** when it trips (the
    attempts are still logged as `empty`, noting the breaker), so the next run asks again.
    The streak is provider-wide (shared by every dataset's `ensure` call), but each withheld
    `empty` is handed over, or logged on a trip, through the callbacks of the call that fetched
    it, so it is persisted under its own dataset. A call that fails for another reason takes back
    only its own withheld empties (logged, not cached); other calls' stay held.
    `ok` resets both streaks, `empty` the error streak, `error` the empty streak; rate limits
    and `unreachable` keep their own thresholds and leave these streaks alone.
  - **Normalise failures are entity errors.** If `normalise` (or the settled cut or version
    append) raises for an `ok` outcome, the store logs an `error` attempt starting
    `normalise:` (exception and payload hash), caches nothing for that item (no raw-response
    row, coverage or facts; the blob may stay) and does not retry it. Other entities are
    persisted as usual; once the provider level finishes, `SourceUnavailable` names the dataset,
    entity, provider and message.
  - **Settled data only.** For time-axis datasets the provider reports, per entity, the
    latest *settled* point (e.g. the last completed trading day in the exchange's
    timezone). Rows after it are not stored as facts and coverage stops there, so a live,
    still-changing bar never becomes an append-only version.
- **Facts are append-only.** Each row carries `provider`, `fetch_id`, `first_seen_at`, and
  `known_at`: the provider-reported publication time (e.g. filing date) when available,
  else `first_seen_at`. A re-fetch or renormalise that changes a row's canonical values **or
  its labels** (`repairs`, `quality`, `quality_reasons`) adds a new version, so restatements
  and relabels are both kept. Facts live in one DuckDB table per dataset, built from
  `Dataset.frame_schema` with typed columns (never JSON rows); bookkeeping columns (`fetch_id`, `first_seen_at`,
  `normaliser_version`, `version_seq`) don't count as a change. The latest version of a key is the one with the greatest `version_seq`, drawn from a store-wide sequence. Each `renormalise` run is logged; it keeps, per key, the row from the newest raw response, so restated keys add nothing when the normaliser is unchanged. `query` serves the first provider in the chain that holds any fact for the request, then applies `as_of` and quality filters (never falling through to a fallback because of them).
- **Coverage = interval sets** per (entity, dataset, provider, params). It records the
  *requested* ranges that were successfully fetched, not the returned dates, so
  weekends/holidays are not "gaps". Gap-fill fetches only the missing intervals, including
  holes in the middle.
- **Fetch-attempt log**: every attempt with outcome and timestamp. `empty` outcomes are
  cached with their own (shorter) TTL, so a delisted entity isn't re-requested every run.
  Errors are not cached.
- **TTL semantics** (pure logic in `lensgraph.sources.coverage`):
  - Settled coverage on a date axis **never expires**. Settled history changes only when
    the provider reports `restated_before` (earlier facts changed; coverage before that day
    is dropped so it is refetched) or through `renormalise`.
  - `Dataset.ttl` (e.g. prices 1 day, profiles 90 days) governs the **unsettled tail**
    (requested days after the last settled day) and **snapshots** (axis "none").
  - `Dataset.empty_ttl` governs `empty` outcomes. `error`, `rate_limited` and `unreachable`
    change nothing and are never cached.
  - Freshness is checked *per requested interval*, not as a global "fetched recently" gate.
- **As-of queries**: `query(dataset, entity, range, as_of)` returns the latest version of
  each key with `known_at` before the end of the `as_of` day (UTC); `as_of=None` is latest. Datasets whose provider can't supply real publication
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
  - `llm_calls` (tokens, cost, attempts): one row per model call made this run (cache hits
    record none); cost from the bundled genai-prices snapshot, NULL for unknown models
  - `plan_nodes`, `plan_edges`: the plan graph (node kind and scope; edge kwarg and optionality),
    written at run start so reports and live views can draw the DAG
  - `campaigns` / `campaign_draws`
- Any citable id resolves to a stored output: `(run_id, candidate, node[, field/item])` → blob.
  That is the drill-down path for "show me the prices behind this claim". Implemented in
  `lineage.resolve_citation`: it needs no table, because a verdict's provenance `input_hashes`
  name the blob behind each cite (`n`, `n.field`, `n[id]`); unresolvable cites raise
  `UnresolvedCitation`.
- Interfaces `BlobStore` and `RunIndex`. The blob store is a single fsspec-backed
  implementation (`FsspecBlobStore`) selected by URL: `file://` locally (`FileBlobStore`),
  `memory://` in tests (`InMemoryBlobStore`), `s3://` with `s3fs` installed. Encoding is
  the same everywhere (Parquet, JSON envelopes, no pickle). The run index is DuckDB;
  Postgres is later. The memo cache *is* the blob store plus an index lookup by memo_key.

## Assessment brief and post-panel review

Decided 2026-11-24 (design only; built in M3, used by campaigns in M7).

- **Assessment brief.** A run-level `AssessmentBrief` states what the assessment is for: purpose,
  horizon, priorities, out-of-scope. It is stated as facts, not a persona ("you are advising...").
  The core model is generic; domains supply fields or templates.
  ```yaml
  brief:
    purpose: "Screen listed equities for a long-only private portfolio"
    horizon: "3–5 years"
    priorities: ["capital preservation", "balance-sheet resilience", "avoid heavy dilution"]
    out_of_scope: ["short-term trading signals", "tax considerations"]
  ```
- **Lenses never see the brief.** Panel lenses assess the *candidate*; the brief judges *fit*.
  This keeps lenses independent evidence (no shared nudge moving every AI lens together) and
  makes panel verdicts reusable across briefs. If a priority needs measuring (e.g. dilution),
  add a component to a deterministic lens rather than putting the brief in a prompt.
- **Where the brief applies**, cheapest first: campaign population filters and strata;
  the acceptance policy (floors, veto rules); and the post-panel reviewer, for fit judgements
  that need reading rather than arithmetic.
- **Post-panel reviewer (`DossierReviewer`).** A separate tier, not a `LensNode` and never in a
  panel. It is a `consumes_verdicts` node that reads the finished dossier plus the brief (and
  optional macro context).
  - Output is a `DossierReview`: a narrative summary, fit to the brief, gaps ("what evidence
    would change this"), and flags from a closed list (e.g. `brief_conflict`). It has **no stance
    and no score**, and every statement cites verdict claims, flags or context ids under the
    same citation guard rail.
  - **It can demote, never promote.** It never changes `overall_stance`. Its flags act only
    through explicit acceptance rules, which the dossier records when they fire.
  - Anchoring risk: a reviewer shown the lens stances tends to echo them. For a summary that's
    fine; any independent fit judgement should be given the evidence and claims, not the stances.
  - Node name `review` (`Panel.reviewer` names the registered class; `panel_registry` wires it
    to the aggregator, and `Panel.targets()` adds it to the run targets). Citable ids:
    `verdict.<lens>`, `verdict.<lens>.claim[<i>]` (0-based) and `flag.<lens>.<code>`. Guard
    rails: unknown cites, flag codes outside the closed list, priorities outside the brief's,
    and any `fit` when there is no brief are retried, then the node fails (no fallback). The
    brief goes in the system prompt, the dossier in the user message; `show_stances=False`
    leaves stances out of the rendered dossier.
  - Its memo key is the dossier hash plus the brief hash. Dossiers carry no `run_id`, so reviews
    rerun only when either changes.
- **Caching:** anything the brief is rendered into must include the brief's hash in its memo key
  and provenance. A template-only prompt hash would serve stale results under a new brief.

## Reporting: run view (one app, one contract)

Decided 2026-11-24. The end-of-run report and the future live view are **the same React app**
reading **the same data contract**.

- **Contract:** `RunView`, a pydantic model (run summary, plan graph, per-candidate `DossierRecord`
  and review, claim-to-citation refs, deduplicated cited values with frames as capped tables,
  LLM calls). Python owns it. A JSON Schema and **generated TypeScript types** come from it, with a
  drift test, so the UI can never silently disagree with the data.
- **Source of truth:** `run.json` (`RunView`), built from the run index and blobs alone, deterministic
  and diffable. A database or API later serves the same shape; nothing else is a second model.
- **Implementation (`lensgraph.view`):** `build_run_view(run_id, index, blobs, max_rows=200)`
  builds the `RunView` from the panel and aggregator named in `run_config`, dossiers and reviews
  via `node_result` and then blobs, and each verdict's cites via `resolve_citation`. A cite that
  cannot be resolved maps to `None`; it never raises. `write_run_view` writes `run.json` and
  `data/run.js` (`window.__RUN__ = <same JSON>;`).
  - Cited values are deduplicated under `CitedView.id` (`<source_hash[:16]>:<cite>`). Frames and
    lists of models become `TableData` (the last `max_rows` rows, `truncated` set); everything
    else is `json_value`. Non-finite floats become null and datetimes ISO strings.
  - `run.json` is byte-deterministic (sorted keys). `RunSummary.llm_cost_usd` is `None` if any
    call's cost is unknown. `RunSummary` status and UTC times come from `RunIndex.run_info`
    (`RunInfo`); each `DossierRecord.created_at` is the run's `finished_at`, else `started_at`,
    and a run with neither is an error (times are never invented). Wall-clock times are the only
    volatile fields, so tests pin them in the index before comparing views.
  - Claim and flag cites are resolved into `cited` (`ClaimRef`, `FlagRef`); a review's cites name
    verdicts, claims and flags rather than stored values, so they are left unresolved.
  - Types: `scripts/gen-types.mjs` (Node, `pnpm dlx json-schema-to-typescript`) writes
    `src/types/run-view.ts` with the schema hash on its first line; `test_view_schema.py`
    compares that hash with `lensgraph.view.schema.schema_hash()` and checks the committed
    `fixtures/toy-run.json` (`LENSGRAPH_REGEN_FIXTURES=1` rewrites it), so Python tests need no Node.
- **`LineChart`** (`lensgraph.charts`) is a core value type (title, shared `x` dates, named
  `series` of floats or null, optional `y_label`) that a node may output and a claim may cite.
  Its view rendering arrives in M5.5.
- **App:** `packages/lensgraph-ui` (React + TypeScript, Vite). UI components are **MUI** (Material UI)
  with **MUI X DataGrid, community edition** (MIT; no Pro features) for tables, and one theme
  (`src/theme.ts`) with light and dark palettes that follow `prefers-color-scheme`; status colours
  (verdict chips, plan nodes) are defined once there. Pages: run summary with a sortable, filterable
  candidate table, the plan graph (React Flow with a dagre layout, coloured by node status), and
  candidate pages (verdict and review cards) with claim-to-cited-data drill-down; cited tables are
  read-only DataGrids and JSON is a monospace block. LLM text is always rendered as text.
  - **List-first navigation (scales to hundreds of candidates):** the summary's candidate grid is the main
    list: quick search, column filters, sorting, and preset chips ("Failures", "Review flags",
    "Contested", "Thin evidence"; thresholds are named constants in `src/presets.ts`; chips combine with
    AND). Rows are virtualised; the community grid pages at 100 rows and the footer shows the row count.
    The list state is kept in the hash query (`#/?sort=share:desc&q=S1&preset=flags&f=field|op|value`),
    so it survives navigation and can be shared. One pure function, `orderedCandidateIds(view, listState)`
    (`src/listOrder.ts`), defines the order; the grid runs in server sort/filter mode and shows exactly
    that order. A candidate page has "Back to list" and Previous/Next (with "12 of 87") that walk the
    same order and carry the list state. The app-bar Autocomplete is a secondary "jump to id" (id,
    overall stance, failure/flag icons).
  - **Two-level plan graph:** the Plan graph tab is the *run level*: one node per node name (edges
    deduplicated by name), each showing its kind and status mix ("97 ok · 3 failed") with a thin stacked
    bar in theme status colours; shared nodes are marked; clicking a node opens a panel listing the
    candidates per status, linking to their pages. Each candidate page has a collapsible *candidate
    level* "Graph" section with only that candidate's node instances plus the shared nodes, coloured by
    status. Node cards carry React Flow Handles (without them no edge is drawn).
  Hash routing (works on `file://`); one store (`src/store.tsx`) fed by the `DataSource`; the plan
  graph is described below. Cited
  values render by `kind` through a hook (`renderers`) that domains extend. Built with
  `pnpm bundle` (Vite single file; emotion injects the styles at runtime); `lensgraph.view.install_app(out_dir)`
  copies the committed bundle (`view/app/index.html`) into a report folder. `BUILD_INFO.json` holds a
  hash of the UI sources (`src/**` plus the build config files, not tests), which `test_view_app.py`
  recomputes, so a UI change without a rebuild fails pytest.
  - **Layout:** `src/` is app code only. Tests live in `tests/unit/` (vitest, mirroring `src/`'s
    folders, with `setup.ts` and `helpers/`); `tests/e2e/` (Playwright) arrives with TASK-22.
    `pnpm typecheck` covers app, build config and tests (`tsconfig.json`, `.node.json`, `.test.json`).
- **Data sources:** the app reads through a `DataSource` interface. `EmbeddedSource` reads
  `window.__RUN__` from `data/run.js` (so the report opens from `file://`, where browsers block
  `fetch`). `FetchSource` reads `run.json` over HTTP. A later `LiveSource` subscribes to run events.
- **Static report:** a folder with the single-file app `index.html`, `run.json` and `data/run.js`;
  no server, works offline, archivable.
- **Live view (later):** run events folded over an empty `RunView` give exactly the final `run.json`,
  so the live view is the report watched as it fills in. See the live-view sketch task.
- **Python users never need Node:** the built bundle is committed into the Python package, with an
  up-to-date check in the Python tests. Only UI development needs Node (pnpm).
- **Cited value renderers:** cited values carry a `kind` and table/JSON payloads, rendered through
  the `renderers` hook by kind. A cited `LineChart` (a whole input or a model field) resolves to kind
  `chart`; `CitedView.chart` holds it (dates as ISO strings, missing y values as null) and the app draws
  it with MUI X Charts: one line per series, date axis, legend, tooltip. A cited model whose fields are
  all scalars (kind `model`, `json_value`) is drawn as a field/value table; nested models stay a JSON
  block. Both are generic: domains only output `LineChart`s and models, and need no app code.

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

**Acceptance is deterministic; review only demotes** (decided 2026-11-24). The acceptance
policy decides. The post-panel reviewer (see Assessment brief and post-panel review) runs only
on candidates that already passed it, and its flags can turn an acceptance into **reject** or
**refer** (a "needs human review" outcome), never the reverse. Quotas count only accepted
candidates. Per-stratum stats add "rejected by review" and "referred", with reasons, and the
shortfall report lists referrals. Vetoed and referred candidates keep their dossiers, so
backtests can check whether review vetoes predict anything.

Memoization makes re-running a campaign with changed quotas cheap: previously evaluated
candidates are cache hits.
