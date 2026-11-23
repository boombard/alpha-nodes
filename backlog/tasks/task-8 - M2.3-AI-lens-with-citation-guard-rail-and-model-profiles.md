---
id: TASK-8
title: M2.3 AI lens with citation guard rail and model profiles
status: In Progress
assignee: []
created_date: '2026-11-23T08:02:58Z'
updated_date: '2026-11-23T23:07:29Z'
labels:
  - core
milestone: m-1
dependencies:
  - TASK-6
references:
  - documentation/design/core.md
type: feature
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec: `documentation/design/core.md`, sections AI nodes (guard rails) and Model profiles. Runs in parallel with task-7, which touches disjoint files.

## Files
- Create: `packages/lensgraph/src/lensgraph/{ai,llm,context}.py`, `packages/lensgraph/tests/toy/safety_lens.py`, `packages/lensgraph/tests/toy/prompts/safety.md.j2`, `packages/lensgraph/tests/toy/prompts/safety_strict.md.j2`
- Modify:
  - `packages/lensgraph/pyproject.toml`: add `pydantic-ai-slim[anthropic,openai]==2.71.0`. The `openai` extra backs pydantic-ai's Ollama provider; verify the extras against the installed package. Also add `jinja2`.
  - `packages/lensgraph/tests/conftest.py`: an autouse fixture that sets `pydantic_ai.models.ALLOW_MODEL_REQUESTS = False`, plus a `scripted_model` fixture factory built on `FunctionModel`.
- Test: `packages/lensgraph/tests/{test_ai_lens,test_llm_profiles,test_context}.py`

## Interfaces
Consumes (task-6): `LensNode`, `LensAssessment`, `Claim`, `Flag`, `Stance`, `Conviction`, `citable_ids`. M1: `Node.memo_salt`, `NodeContext.services`, `run`, `RunSpec`.

Produces:
```python
# llm.py
class LLMProfile(BaseModel):   # renamed from ModelProfile 2026-11-24 (clashes with pydantic_ai.profiles.ModelProfile)
    name: str; model: str; settings: dict[str, Any] = {}
    output_mode: Literal["tool", "native", "prompted"] = "tool"; max_retries: int = 2
DEFAULT_PROFILES: dict[str, LLMProfile]
#   dev     -> model="anthropic:claude-haiku-5-5", settings={"thinking": "low"}
#   quality -> model="anthropic:claude-sonnet-5-5", settings={"thinking": "medium"}
#   local   -> model from settings env LENSGRAPH_LOCAL_MODEL (e.g. "ollama:qwen3:8b"), output_mode="prompted";
#              resolving it when unset raises ValueError naming the env var
class ProfileRegistry:
    def __init__(self, profiles: Mapping[str, LLMProfile] | None = None,
                 model_overrides: Mapping[str, Any] | None = None) -> None   # override: profile name -> pydantic-ai Model instance
    def get(self, name: str) -> LLMProfile
    def model_for(self, name: str) -> Any               # override instance, else the profile's model string
    def fingerprint(self, name: str) -> str             # content_hash of model id/override type + settings + output_mode
# context.py
def render_context(inputs: Mapping[str, Any], depth_notes: Mapping[str, str] | None = None,
                   *, max_rows: int = 50) -> str
# ai.py
class AIAssessmentOut(BaseModel):                       # the LLM-facing schema
    status: Literal["ok", "abstained"]; stance: Stance | None = None; conviction: Conviction | None = None
    claims: list[Claim] = []; flags: list[Flag] = []; abstain_reason: str | None = None
class AINode(LensNode):
    prompt: ClassVar[Path]; variants: ClassVar[dict[str, Path]] = {}
    flag_codes: ClassVar[frozenset[str] | None] = None; resource = "llm"
    profile: str = "dev"; variant: str = "default"
    def memo_salt(self, services) -> str   # profiles fingerprint + prompt template hash
# tests/toy/safety_lens.py
class SafetyLens(AINode): name = "safety_lens"; lens_name = "safety"
    inputs = {"growth_rate": "growth_rate"}; optional_inputs = {"tox_notes": "tox_notes"}
    depth = {"tox_notes": DepthRequirement(desired=3, minimum=1)}; flag_codes = frozenset({"tox_signal"})
```
Semantics:
- **Profile lookup:** profiles come from `ctx.services["profiles"]` (a `ProfileRegistry`), falling back to a default `ProfileRegistry()`.
- **Prompt:** the template (Jinja2) is `variants.get(variant, prompt)`. The rendered template is the **system prompt**, static content first so provider prompt caching applies. The user message is `render_context(...)` plus the depth notes, e.g. `"tox_notes: 1 of 3 desired items"`.
- **`render_context`:**
  - Each citable id gets a block headed `### [<id>]`, ordered by input name.
  - DataFrames render as CSV of the last `max_rows` rows, with the note `(showing last N of M rows)`.
  - Models render as JSON, one block per field id.
  - List items get one block each.
  - An `Absent` input renders as `### <name>: NOT AVAILABLE (<reason>)` and is **not** citable.
- **Agent:** `Agent(model, output_type=<AIAssessmentOut wrapped per output_mode: ToolOutput / NativeOutput / PromptedOutput>, retries=profile.max_retries)`, with `model_settings` from the profile.
- **The guard rail** is an `@agent.output_validator` that raises `ModelRetry(...)` in four cases:
  - a citation is not in `citables`, with the message `"Unknown citation ids: [...]. Valid ids: [...]"`. Matching is exact; ids are never case-folded.
  - a flag code is not in `flag_codes`, when that is set
  - the status is ok but stance or conviction is missing
  - a claim has no citations
- **Exhausted retries:** pydantic-ai raises; let it propagate, so the executor marks the node `failed`.
- **One sample per call.** The verdict's `stance_mean` comes from the LensNode template default (`float(stance)`), and `stance_spread` stays None. Repeated sampling (N runs, mode/mean/spread, `stance_samples`) is deferred to TASK-17 (human decision, 2026-11-23). Keep `assess` structured so one run is one function call that TASK-17 can repeat.
- **`provenance_extra`:** `{model, model_settings, prompt_hash, variant, attempts, input_tokens, output_tokens}`. Attempts is the number of model requests made. Tokens come from `result.usage()`.

## Steps
- [ ] Write the failing tests. Use FunctionModel scripts via `scripted_model` and register them with `ProfileRegistry(model_overrides={"test": model})` plus a `test` profile:
  - `test_first_answer_bad_citation_retried_then_ok`: `attempts == 2`, and every cite is in the citable set.
  - `test_retries_exhausted_fails_node`: the model always cites `"made_up"`. The `NodeResult` status is `failed` and the error mentions citation. The run completes.
  - `test_citation_case_variant_rejected`: `"Growth_Rate"` triggers a retry, and the retry prompt text contains `Valid ids:` and `growth_rate`.
  - `test_unknown_flag_code_rejected`
  - `test_abstain_allowed_maps_to_abstained_verdict`
  - `test_absent_optional_input_rendered_not_available_and_not_citable`: S2 has empty `tox_notes`, so the safety verdict's coverage is below 1.
  - `test_profile_change_invalidates_ai_memo_only`: changing the test profile's settings reruns `safety_lens`, while `growth_rate` is a cache hit.
  - `test_variant_changes_prompt_hash`: `{"safety_lens": {"variant": "strict"}}`.
  - `test_dev_profile_is_default_and_cheapest`: `SafetyLens().profile == "dev"`; `DEFAULT_PROFILES["dev"].model == "anthropic:claude-haiku-5-5"`; `DEFAULT_PROFILES["dev"].settings == {"thinking": "low"}`.
  - `test_local_profile_requires_env`
  - `test_render_context_frame_truncation`
  - `test_no_real_model_requests_allowed`: a `SafetyLens` on the `dev` profile with no override fails the node, with no network call.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_ai_lens.py packages/lensgraph/tests/test_llm_profiles.py packages/lensgraph/tests/test_context.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run the tests above, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): AI lens with citation guard rail and model profiles`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Invalid citations, unknown flag codes and incomplete ok answers trigger ModelRetry; exhausted retries fail the node
- [ ] #2 dev profile is the default (anthropic:claude-haiku-5-5, thinking low); local (Ollama) and quality profiles exist
- [ ] #3 Profile fingerprint and prompt hash are part of the AI memo key and provenance
- [ ] #4 No test can make a real model request (ALLOW_MODEL_REQUESTS=False)
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
Worker: dispatch ctx_0aee45aac7a5, worktree task-8

Back to In Progress (human request, 2026-11-24): rename ModelProfile to LLMProfile (clash with pydantic_ai.profiles.ModelProfile) and add per-profile UsageLimits. Cost via genai-prices noted in TASK-10; FallbackModel noted in TASK-13.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_0aee45aac7a5, branch boom/task-8, 2 commits b8db94c..1213b0c): llm.py (ModelProfile, DEFAULT_PROFILES dev/quality/local, ProfileRegistry with fingerprint and test overrides), context.py (render_context, unavailable_inputs), ai.py (AIAssessmentOut, guard_rail, AINode with memo_salt, one model call per run), toy SafetyLens with two prompt variants, conftest (autouse ALLOW_MODEL_REQUESTS=False, scripted_model); pydantic-ai-slim[anthropic,openai]==2.71.0 and jinja2 added; core.md updated. ACs 1-4 met (test_first_answer_bad_citation_retried_then_ok, test_unknown_flag_code_rejected, test_ok_without_stance_or_conviction_retried, test_retries_exhausted_fails_node, test_citation_case_variant_rejected (Review Focus 4); test_dev_profile_is_default_and_cheapest, test_quality_profile_*, test_local_profile_requires_env; test_profile_change_invalidates_ai_memo_only, test_variant_changes_prompt_hash; test_no_real_model_requests_allowed). Coordinator re-ran checks: pytest 186 passed, ruff clean, pyright 0 errors; merges cleanly with boom/task-7. Checked that 'thinking' is a valid unified ModelSettings key in pydantic-ai 2.71.
Coordinator review, one fix round: an undeclared prompt variant is now a ParamsError at plan time (it used to fall back silently to the default prompt). Reviewed by hand (ai, llm, context in full); the code-review skill was not run.
Worker rulings: (1) core.md edited (DoD). (2) The local profile model is the sentinel 'env:LENSGRAPH_LOCAL_MODEL', resolved in ProfileRegistry.get with os.environ. (3) When retries run out, UnexpectedModelBehavior is re-raised with the last rejection appended. (4) Empty lists and Absent inputs render NOT AVAILABLE and are removed from the citable set, so a legitimately empty list is uncitable. (5) Small helpers describe_model() and unavailable_inputs(). (7) The guard rail's no-cites check is unreachable (the schema already requires min_length=1) and is kept as a safety net.
Open points: an unknown profile name fails per candidate at run time, not at plan time (the registry is a run-time service). Input text (e.g. news) goes into prompts unescaped; the citation guard rail limits damage, but prompt injection should be reviewed when real text sources arrive (M6).
<!-- SECTION:FINAL_SUMMARY:END -->
