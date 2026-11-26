---
id: TASK-64
title: 'Finance glossary: seed entries for every price and fundamentals field'
status: In Progress
assignee: []
created_date: '2026-11-26T00:28:00Z'
updated_date: '2026-11-26T04:09:09Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-63
  - TASK-51
  - TASK-53
  - TASK-55
  - TASK-56
  - TASK-61
  - TASK-66
references:
  - documentation/design/finance.md
type: feature
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The finance glossary content (finance.md "Glossary", added by this task), in the always-on data-dictionary format
of core.md "Glossary" (TASK-66). One entry per term behind every field that reaches an AI lens, plus every citable
field of the price result models, all `status: draft` (written from model knowledge; research upgrades them later):
- result models: price (Momentum, Trend, Volatility, Drawdown) and fundamentals (Profitability, BalanceSheet,
  CashGeneration, FundamentalTrend, Valuation, ValuationChange);
- the `annual_fundamentals` frame columns (`AnnualFundamentalsSchema`, incl. inherited `FundamentalsSchema` line
  items: revenue, operating_income, net_income attributable to common, interest_expense positive = cost, capex
  positive = cash spent, total_equity incl. minority interest, shares_diluted weighted average, ...): these are
  our conventions too, so each line item gets an entry claimed on `FundamentalsSchema.<column>`; statement
  metadata (period_type, period_end, filed_at, currency, suspect) shares one "statement row" entry, claimed
  field by field;
- the `profile` frame (`ProfileSchema`): one "listing profile" entry, whole-model claim.
Window fields share one entry each for "price window" and "period window", as whole-model claims on
`PriceWindow` and `PeriodWindow` (inherited fields resolve to the base; see core.md, Claims). `recent_news` has
a bare `list` contract, so it contributes no fields (leave it).

Lenses no longer declare terms: each AI lens sets `glossary = FINANCE_GLOSSARY_DIR` and its dictionary is derived
from its inputs at plan build. Prompt notes follow core.md: what the number is in our data (basis, window, units
with "0.15 means 15%", sign, fallbacks) plus at most one caution. The per-term formulas in finance.md move into the
entries and the bullets link them. The prompts keep instructions only: the `field_periods` sentence in both
prompt templates loses its definition (now in the period-window note) and keeps the instruction, e.g. "Weigh
fields listed in `field_periods` less, lower your conviction when key fields are stale, and say so."
Roughly 40-50 entries (more than first planned, because frame columns now count), each with a `summary` and a
`category` (price, profitability, leverage, cash generation, growth, valuation, statement, window), formulas in
`$...$` math, and cross-references as relative `.md` links.

## Files
- Create: `packages/alpha_nodes/src/alpha_nodes/glossary/*.md` (entries) and `glossary/__init__.py`
  (`FINANCE_GLOSSARY_DIR = Path(__file__).parent`; no load at import); package-data config in
  `packages/alpha_nodes/pyproject.toml` if needed so the .md files ship
- Modify: `lenses/quality_value.py`, `lenses/price_vs_fundamentals.py` (`glossary = FINANCE_GLOSSARY_DIR`);
  `prompts/quality_value.md.j2`, `prompts/quality_value_buffett_persona.md.j2` (if it has the line),
  `prompts/price_vs_fundamentals.md.j2` (`field_periods` sentence: instruction only);
  `documentation/design/finance.md` (section B); `documentation/README.md` (link); `backlog/docs/doc-1` is the
  coordinator's (line C)
- Test: `packages/alpha_nodes/tests/test_glossary_finance.py`
- Added in review (user, 2026-11-26): `packages/lensgraph/src/lensgraph/node.py`, `graph.py`, `sources/node.py`, `packages/alpha_nodes/src/alpha_nodes/nodes/fetch.py`, `documentation/design/core.md` (Glossary), a lensgraph test (`test_glossary.py` or `test_source_node.py`); also accepted: `tests/ai_lens_helpers.py`, `test_quality_value_lens.py`, `test_price_vs_fundamentals_lens.py`

## Steps
- [ ] Failing tests: `test_finance_glossary_loads`, `test_every_result_field_has_one_entry` (iterates the result
  models in alpha_nodes.metrics, excluding nothing; resolves with `Glossary.term_for`),
  `test_ai_lens_plans_build` (build a plan with each AI lens from the real registry: no uncovered field),
  `test_no_unresolved_claims` (`unresolved_claims` over every node `output` in the registry is `[]`),
  `test_implemented_by_resolves`, `test_no_whole_model_claim_on_metric_models` (whole-model claims only on
  PriceWindow, PeriodWindow, ProfileSchema), `test_prompt_notes_have_no_formulas` (no `=`, and no ` + `,
  ` * `, ` / ` between spaces), `test_prompts_do_not_define_field_periods` (the definition sentence is gone).
- [ ] Run. Expected: FAIL.
- [ ] Write the entries; wire the lenses; trim the prompt sentences; edit finance.md (move formulas, link
  entries; keep policy text). Field comments in `datasets.py` / `metrics.py` that define a convention may stay
  short and point to the entry.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`; `uv run lensgraph glossary
  packages/alpha_nodes/src/alpha_nodes/glossary` lists every entry as draft. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): finance glossary seeded for price and fundamentals fields`.

Out of scope: researching and verifying entries (later, per term); typing `recent_news` as `list[NewsItem]`.
Expected side effect: both AI lenses' prompts change, so their cached verdicts miss once.

Design text for finance.md (write it in this task): the approved draft, copied below.

## B. finance.md: changes

- New short section "Glossary": the finance glossary lives in
  `packages/alpha_nodes/src/alpha_nodes/glossary/` (package data); every field that reaches an
  AI lens, and every citable field of the price and fundamentals result models, resolves to
  exactly one entry (tested, and checked at plan build). AI lenses get their data dictionary
  from their inputs; they declare no term lists.
- "Fundamentals: pinned conventions" and the price_behaviour metric definitions: per-term
  formulas move to their entries; the bullets keep the policy and link the entry
  (e.g. "**FCF**: see glossary `fcf`; capex sign pinned positive, see Providers").
- Calculation layers: a new calc field, or a new column of a frame an AI lens reads, needs a
  glossary entry in the same task (a missing one fails the plan).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every citable price and fundamentals result field has exactly one entry; all entries validate and their implemented_by paths resolve
- [ ] #2 Plans with quality_value and price_vs_fundamentals build: every input field, frame columns included, resolves to an entry; neither lens lists terms
- [ ] #3 finance.md per-term formulas live in the entries; the conventions keep policy and link them
- [ ] #5 build_plan binds a dataset fetch node's frame columns (Node.contract), so the profile columns reach the glossary check and the data dictionary
- [ ] #4 Prompt notes are interpretive, state units, sign and window where relevant, and contain no formulas; prompt templates no longer define field_periods
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
Worker: dispatch ctx_1ed3c5c919f0, worktree task-64 (Orca run run_cce261b5aaf8)

Review round 2 (user ruling 2026-11-26): fold the core fetch-contract gap into TASK-64: Node.contract(), DatasetFetch frame_schema, graph.py binds via contract().
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (ctx_1ed3c5c919f0, follow-up ctx_6584a99a984a): 54 draft finance glossary entries + FINANCE_GLOSSARY_DIR; both AI lenses set glossary and declare no terms; field_periods definition dropped from the 3 prompts (instruction kept); finance.md per-term formulas moved into entries and linked, new Glossary section; README link. Commits b186408, 5821637, b7e9e59 (squash on landing). pytest 1135 passed, ruff clean, pyright 0; the wheel ships 54 glossary .md files (no pyproject change). Review: 1 round, 4 findings, all resolved: (1) the TR-index recursion was lost from finance.md, so a new total-return-index entry claims the TotalReturnSchema columns; (2) the lens test contracts now come from the node classes' outputs, with stand-ins only for valuation/valuation_change until TASK-54; (3) test cleanup; (4) the wheel contents were verified. Accepted outside Files: ai_lens_helpers.py, test_quality_value_lens.py, test_price_vs_fundamentals_lens.py (the lens tests must bind the glossary). Verdict: approve. Open points: (a) a core gap: graph.py:180 binds the fetch nodes' output (bare pd.DataFrame), so in real plans the profile columns are neither checked nor put in the data dictionary; (b) the Valuation/ValuationChange entries have an empty implemented_by, and the test helper's stand-ins are for TASK-54 to fill and drop; (c) both AI lens prompts change, so their verdicts miss the cache once.
<!-- SECTION:FINAL_SUMMARY:END -->
