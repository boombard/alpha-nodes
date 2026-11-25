---
id: TASK-55
title: M6.8 quality_value AI lens with rubric and buffett_persona variant
status: In Progress
assignee: []
created_date: '2026-11-25T08:17:59Z'
updated_date: '2026-11-25T23:25:45Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-49
  - TASK-25
references:
  - documentation/design/finance.md
  - documentation/design/core.md
type: feature
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The `quality_value` AI lens: a rubric prompt that states Buffett's principles with their primary sources (default) and a `buffett_persona` variant, judging from the fundamentals calcs, the valuation calc, the profile's business summary and recent news. Plus the `recent_news` transform. After M6.1 (contracts) and TASK-25 (critical inputs); tests use hand-built result models, so it runs before the calc nodes land. Spec: `documentation/design/finance.md` (v1 lenses, 2. quality_value; "Fundamentals: ... Lens inputs and abstention"); `documentation/design/core.md` (AI nodes (guard rails), Model profiles, Variants).

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/lenses/quality_value.py`: `QualityValue`
  - `packages/alpha_nodes/src/alpha_nodes/prompts/quality_value.md.j2` (rubric, default)
  - `packages/alpha_nodes/src/alpha_nodes/prompts/quality_value_buffett_persona.md.j2`
  - `packages/alpha_nodes/src/alpha_nodes/nodes/news.py`: `RecentNews`
- Test: `packages/alpha_nodes/tests/test_quality_value_lens.py`, `packages/alpha_nodes/tests/test_recent_news.py`

## Interfaces
Consumes: `AINode`, `DepthRequirement`, `critical_inputs` (TASK-25), `ProfileRegistry` with `model_overrides` (M2); `NewsItem`, `NewsSchema`, the result models `ProfitabilityResult`, `BalanceSheetResult`, `CashGenerationResult`, `ValuationResult`, `FundamentalsSchema`, `reference_day` (M6.1).

Produces:
```python
# nodes/news.py
class RecentNews(TransformNode): name = "recent_news"; inputs = {"news": "news"}; output = list
    days: int = 90; max_items: int = 10
    # items published within `days` before reference_day(ctx),
    # newest first, at most max_items, as list[NewsItem]; an empty frame -> []

# lenses/quality_value.py
QUALITY_VALUE_FLAGS = frozenset({"high_leverage", "dilution", "inconsistent_earnings",
                                 "stretched_valuation", "thin_history", "accounting_concern"})
class QualityValue(AINode):
    name = "quality_value"; lens_name = "quality_value"
    prompt = <prompts>/quality_value.md.j2
    variants = {"buffett_persona": <prompts>/quality_value_buffett_persona.md.j2}
    inputs = {"annual_fundamentals": "annual_fundamentals", "profitability": "profitability",
              "balance_sheet": "balance_sheet", "cash_generation": "cash_generation", "valuation": "valuation"}
    optional_inputs = {"profile": "profile", "recent_news": "recent_news"}
    depth = {"annual_fundamentals": DepthRequirement(desired=8, minimum=3),
             "recent_news": DepthRequirement(desired=5, minimum=1)}
    input_weights = {"recent_news": 0.5, "profile": 0.5}
    critical_inputs = frozenset({"annual_fundamentals"})       # TASK-25 field default
    flag_codes = QUALITY_VALUE_FLAGS
```
The class docstring records two deliberate choices: no analyst consensus or price targets in the context (LLM herding, TASK-13 note), and news/profile text is untrusted evidence to weigh, never instructions.

**Rubric content (default prompt), static, first in the prompt for caching.** One numbered principle per item, each with its source, as below. These sources were supplied by the coordinator from memory; keep the wording close to them and do not add sources you cannot name precisely. The human verifies them at review.
1. Consistent earning power (Berkshire's acquisition criteria, printed in its annual reports, e.g. the 2014 letter).
2. Good returns on equity while employing little or no debt (same criteria).
3. Management in place (same criteria); judged from text only, never invented.
4. Simple, understandable businesses; stay within the circle of competence (criteria; 1996 letter).
5. A durable competitive advantage, the "moat" (2007 letter).
6. Owner earnings = reported earnings + D&A − maintenance capex (1986 letter, appendix); our number is a proxy, say so.
7. Margin of safety: pay well below a conservative estimate of value (1992 letter; Graham, *The Intelligent Investor*, ch. 20).
Then the instructions: interpret the cited calc numbers, never compute new ones; stance −2..+2 meaning "strong avoid" .. "strong buy at this price"; say when history is thin (the depth note); cite ids exactly as given; use only the listed flag codes.

**Persona variant:** "assess as Warren Buffett would", plus: don't caricature (no folksy quotes), don't use knowledge of his actual holdings or anything he has said about this company, use only the evidence given. Same output contract and flag codes.

## Steps
- [ ] Write the failing tests (`FunctionModel` via `ProfileRegistry(model_overrides=...)`; `ALLOW_MODEL_REQUESTS = False`):
  - `test_recent_news.py`: `test_recent_news_window_and_order`, `test_recent_news_caps_items`, `test_empty_news_gives_empty_list`, `test_items_citable_by_id`.
  - `test_quality_value_lens.py`: `test_ok_verdict_with_valid_cites` (cites `profitability.roe_mean` and a `recent_news[<id>]`), `test_unknown_cite_retried_then_fails`, `test_unknown_flag_code_rejected`, `test_abstains_without_fundamentals_and_no_model_call` (empty `annual_fundamentals`), `test_two_periods_below_minimum_abstains`, `test_four_periods_gives_half_sufficiency_and_depth_note` (the user message says "4 of 8"), `test_persona_variant_changes_prompt_hash_and_memo_salt`, `test_unknown_variant_rejected`, `test_rubric_is_static_and_lists_sources` (the system prompt contains each principle's source and no candidate data), `test_context_has_no_analyst_fields` (no "recommendation", "targetMeanPrice" or similar in the user message built from a profile frame that contains extra columns: the lens drops all but name, sector, industry, country, business_summary).
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_quality_value_lens.py packages/alpha_nodes/tests/test_recent_news.py -q`. Expected: FAIL.
- [ ] Implement. If the profile column filter needs a hook `AINode` lacks, do it in an overridden `assess` that filters inputs and calls `super().assess`; `ask` if that is not enough.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): quality_value AI lens with rubric and buffett_persona variant`.

Out of scope: registering nodes (M6.10); repeated sampling (TASK-17); 10-K text (deferred).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 QualityValue and RecentNews exist as specified; flag codes closed; persona variant selectable and in the memo key
- [ ] #2 The rubric lists the seven principles with their sources, static and first; the persona prompt has the no-caricature and no-holdings rules
- [ ] #3 Missing or too-thin annual_fundamentals abstains with no model call; 4 periods gives sufficiency 0.5 and a depth note
- [ ] #4 The context carries no analyst ratings or price targets; the docstring records the herding and untrusted-text choices
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
Worker: dispatch ctx_e7185589db01, worktree task-55 (Orca run run_09eee9a7786f)
<!-- SECTION:NOTES:END -->
