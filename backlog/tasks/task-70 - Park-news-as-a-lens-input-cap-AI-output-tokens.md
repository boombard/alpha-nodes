---
id: TASK-70
title: Park news as a lens input; cap AI output tokens
status: In Review
assignee: []
created_date: '2026-11-26T09:25:35Z'
updated_date: '2026-11-26T09:35:03Z'
labels:
  - finance
  - core
milestone: m-5
dependencies: []
priority: high
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Human feedback from the M6 demo (2026-11-26). Two cost cuts before the M6 gate is signed off.

**1. Park news as a lens input.** As fed today (up to 10 items x 90 days, full summaries), news is not selective and costs too many tokens for what it adds. `quality_value` stops taking `recent_news`. The code stays and stays tested: the `news` dataset, the yfinance news adapter, the `News` fetch node, `RecentNews`, and their glossary entries. Nothing in the M6 run fetches news any more. TASK-71 (sketch) holds the redesign.

**2. Cap AI output tokens.** Measured on the M6 demo (dev/Haiku, 30 calls): about 1,800 output tokens for a call that passes first time, 2,600 with one retry, 4,300 with two; 1.4-1.5 attempts on average. Output (thinking included) is about 40% of the cost. Three caps, all on the profile so every AI node gets them (lenses and the reviewer):
- per response: `max_tokens` in the profile settings (proposed `dev` 2,500, `quality` 4,000).
- per call, all retries: `UsageCaps.output_tokens_limit` (proposed `dev` 6,000, `quality` 10,000). `local` gets the same ceilings as `dev`.
- what the model writes: AI lens answers carry at most `max_claims` claims (default 5) and claim text of at most `max_claim_chars` characters (default 300). Both go into the output JSON schema the model sees and are stated in the prompt, so it doesn't have to be sent back.

Hitting a cap fails the node (`UsageLimitExceeded`, or a truncated answer that fails schema validation). No fallback, no partial verdict.

## Files
- Modify: `packages/alpha_nodes/src/alpha_nodes/lenses/quality_value.py` (drop `recent_news` from `optional_inputs`, `depth`, `input_weights`; docstring), `prompts/quality_value.md.j2`, `prompts/quality_value_buffett_persona.md.j2` (no news line), `runs/m6_fundamentals.yaml` (no `news` provider)
- Modify: `packages/lensgraph/src/lensgraph/llm.py` (default profiles: `max_tokens`, `output_tokens_limit`), `packages/lensgraph/src/lensgraph/ai.py` and/or `lens.py` (claim count and length bounds in the output contract and prompt; truncated responses fail)
- Modify: `documentation/design/core.md` (Model profiles: the output caps and why), `documentation/design/finance.md` (quality_value text inputs: news parked, see TASK-71)
- Test: `packages/lensgraph/tests/test_llm.py`, `test_ai*.py`; `packages/alpha_nodes/tests/test_quality_value_lens.py`, `ai_lens_helpers.py`, `test_m6_e2e.py`

## Steps
- [ ] Failing tests: `test_quality_value_takes_no_news`, `test_m6_plan_fetches_no_news`, `test_default_profiles_cap_output_tokens`, `test_output_tokens_limit_fails_the_node` (FunctionModel over the limit), `test_truncated_answer_fails_the_node`, `test_too_many_claims_fails_schema`, `test_output_schema_states_claim_bounds`.
- [ ] Run. Expected: FAIL.
- [ ] Implement. Check how pydantic-ai passes `max_tokens` next to `thinking` for Anthropic (the thinking budget must fit inside `max_tokens`); if the proposed numbers don't fit, ask rather than pick.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS. Render one quality_value user message from a fixture and report its token count before and after.
- [ ] Commit: `feat: park news input and cap AI output tokens`.

Expected side effect: the prompts, output schema and profile fingerprints change, so every AI verdict misses the cache once.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 quality_value no longer takes recent_news; the M6 run fetches no news; news code and tests stay
- [ ] #2 Default profiles cap output tokens per response (max_tokens) and per call (output_tokens_limit)
- [ ] #3 AI lens answers are bounded in claim count and claim length, in the output schema and the prompt
- [ ] #4 Exceeding a cap or a truncated answer fails the node with no fallback
- [ ] #5 core.md and finance.md describe the caps and the parked news input
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
Worker: dispatch ctx_ee1f2bee3060, worktree task-70 (Orca run run_5e68c868c3a6). Stale base 7454545 fast-forwarded to ba53f3d at start.

Worker done 9d59975 (1285 passed). Round 1 sent (follow-up dispatch ctx_f51cfd4e7fb4): prompt grammar 'them'->'it'. toy-run.json regenerated outside Files (accepted: toy prompt hash changed).

Round 2 sent: same prompt line, 'found in them' -> 'found in it'.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: quality_value drops recent_news (prompts, run yaml; news code and tests kept, TASK-71 sketch for the redesign); default profiles cap output tokens per response (max_tokens dev/local 2500, quality 4000) and per call (output_tokens_limit 6000/10000); AINode params max_claims=5, max_claim_chars=300 go into the output schema (assessment_schema) and a system-prompt line for every AI lens; caps and truncation fail the node; core.md + finance.md updated. 1285 passed, ruff/pyright clean. Review: 1 round (prompt grammar). Verdict: approve. Single commit b9cfb52. Rulings accepted: Haiku/Sonnet 5.5 use adaptive thinking (verified in pydantic-ai profiles), so no budget_tokens to fit; toy-run.json regenerated outside Files. Expected: every AI verdict misses the cache once. Open: real token saving to be measured on the M6 demo re-run.
<!-- SECTION:FINAL_SUMMARY:END -->
