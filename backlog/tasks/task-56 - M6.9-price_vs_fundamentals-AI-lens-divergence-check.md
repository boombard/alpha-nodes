---
id: TASK-56
title: M6.9 price_vs_fundamentals AI lens (divergence check)
status: To Do
assignee: []
created_date: '2026-11-25T08:18:00Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-49
  - TASK-25
references:
  - documentation/design/finance.md
type: feature
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The `price_vs_fundamentals` AI lens, framed as a divergence check so momentum isn't double-counted: does the price action agree with the fundamental trend and the change in valuation? After M6.1 (contracts) and TASK-25 (critical inputs); tests use hand-built result models. Spec: `documentation/design/finance.md` (v1 lenses, 3. price_vs_fundamentals; "Fundamentals: ... Lens inputs and abstention"); `documentation/design/core.md` (AI nodes (guard rails)).

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/lenses/price_vs_fundamentals.py`
  - `packages/alpha_nodes/src/alpha_nodes/prompts/price_vs_fundamentals.md.j2`
- Test: `packages/alpha_nodes/tests/test_price_vs_fundamentals_lens.py`

## Interfaces
Consumes: `AINode`, `DepthRequirement`, `critical_inputs` (TASK-25), `ProfileRegistry` (M2); `MomentumResult`, `TrendResult` (M5); `FundamentalTrendResult`, `ValuationChangeResult`, `FundamentalsSchema` (M6.1).

Produces:
```python
FLAG_SEVERITY: dict[str, Literal["info", "warn"]] = {
    "price_up_fundamentals_down": "warn",
    "rerating_despite_deterioration": "warn",
    "price_down_fundamentals_up": "info",
    "derating_despite_improvement": "info",
}
class PriceVsFundamentals(AINode):
    name = "price_vs_fundamentals"; lens_name = "price_vs_fundamentals"
    prompt = <prompts>/price_vs_fundamentals.md.j2
    inputs = {"momentum": "momentum", "trend": "trend", "fundamental_trend": "fundamental_trend",
              "valuation_change": "valuation_change", "annual_fundamentals": "annual_fundamentals"}
    depth = {"annual_fundamentals": DepthRequirement(desired=4, minimum=2)}
    critical_inputs = frozenset({"annual_fundamentals"})
    flag_codes = frozenset(FLAG_SEVERITY)
    # assess(): super().assess, then each flag's severity is set from FLAG_SEVERITY (framework-owned, like status)
```
Stance meaning (in the prompt): +2 = the fundamentals strongly support the price action and current valuation; 0 = mixed or no clear divergence; −2 = the price has run well ahead of (or against) deteriorating fundamentals. The prompt says the momentum numbers are context for the comparison, not a reason to be bullish by themselves, and carries the TASK-61 line: "Fields listed in a result's `field_periods` come from an older period than its `last_period_end`; weigh them accordingly, lower your conviction when key fields are stale, and say so."

## Steps
- [ ] Write the failing tests (`FunctionModel`, `ALLOW_MODEL_REQUESTS = False`):
  `test_ok_verdict_with_valid_cites`, `test_flag_severity_overridden_from_code` (the model says `info` for `price_up_fundamentals_down`; the verdict has `warn`), `test_unknown_flag_code_rejected`, `test_abstains_with_one_period_and_no_model_call`, `test_depth_note_rendered` ("2 of 4"), `test_prompt_states_divergence_framing` (the system prompt contains the stance scale and the flag list), `test_docstring_records_no_analyst_inputs`, `test_prompt_mentions_field_periods`.
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_price_vs_fundamentals_lens.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): price_vs_fundamentals AI lens (divergence check)`.

Out of scope: registering nodes (M6.10); quarterly trends.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 PriceVsFundamentals exists as specified with the four flag codes; severities are set from FLAG_SEVERITY, not by the model
- [ ] #2 Fewer than 2 known annual periods abstains with no model call; depth note rendered
- [ ] #3 The prompt states the divergence framing and the stance scale
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
