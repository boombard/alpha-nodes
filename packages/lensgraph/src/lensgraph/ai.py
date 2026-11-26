"""AINode: an LLM-backed lens whose answer must pass schema and citation guard rails.

See documentation/design/core.md, AI nodes (guard rails). The model never produces numbers
used in scoring; its structured answer is validated against the closed set of citable ids and
retried by pydantic-ai, or the node fails (no placeholder fallback).
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, ClassVar, Literal, Self

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, PrivateAttr, model_validator
from pydantic_ai import Agent, ModelRetry, NativeOutput, PromptedOutput, ToolOutput
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.settings import ModelSettings

from .context import render_context, unavailable_inputs
from .glossary import Glossary, GlossaryError, contract_model, model_fields
from .hashing import content_hash
from .lens import LensAssessment, LensNode
from .llm import ProfileRegistry, describe_model
from .node import NodeContext
from .types import Absent
from .verdict import Claim, Conviction, Flag, Stance

_JINJA = Environment(undefined=StrictUndefined, keep_trailing_newline=True)


class AIAssessmentOut(BaseModel):
    """The LLM-facing answer schema: a subset of `LensVerdict`.

    The framework fills lens, status "failed", coverage, score and provenance itself.
    """

    status: Literal["ok", "abstained"]
    stance: Stance | None = None
    conviction: Conviction | None = None
    claims: list[Claim] = []
    flags: list[Flag] = []
    abstain_reason: str | None = None


def _output_spec(mode: str, output_type: type[BaseModel]) -> Any:
    """Wrap `output_type` for the profile's output mode."""
    wrapper = {"tool": ToolOutput, "native": NativeOutput, "prompted": PromptedOutput}[mode]
    return wrapper(output_type)


async def call_structured(
    *,
    registry: ProfileRegistry,
    profile_name: str,
    output_type: type[BaseModel],
    system_prompt: str,
    user_message: str,
    validate: Callable[[Any], Any],
) -> tuple[Any, dict[str, Any]]:
    """One guard-railed structured model call, shared by `AINode` and the dossier reviewer.

    Builds the agent from the named profile (output mode, retries, settings, usage limits),
    runs `validate` as the output validator (it raises `ModelRetry` to ask the model again) and
    returns the validated output plus provenance fields (model, settings, attempts, tokens).
    Callers add their own `prompt_hash` and `variant`. Exhausted retries raise
    `UnexpectedModelBehavior` naming the last rejection; there is no fallback.
    See documentation/design/core.md, AI nodes (guard rails).
    """
    profile = registry.get(profile_name)
    model = registry.model_for(profile_name)
    agent: Agent[None, Any] = Agent(
        model,
        output_type=_output_spec(profile.output_mode, output_type),
        system_prompt=system_prompt,
        retries=profile.max_retries,
        model_settings=ModelSettings(**profile.settings),  # type: ignore[typeddict-item]
    )
    agent.output_validator(validate)
    try:
        result = await agent.run(
            user_message,
            usage_limits=profile.usage_limits.to_limits() if profile.usage_limits else None,
        )
    except UnexpectedModelBehavior as exc:
        if exc.__cause__ is None:
            raise
        # Keep the last rejection (e.g. the unknown citation ids) in the node's error.
        raise UnexpectedModelBehavior(f"{exc.message}; last rejection: {exc.__cause__}") from exc
    usage = result.usage
    return result.output, {
        "model": describe_model(model),
        "model_settings": profile.settings,
        "attempts": usage.requests,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


def guard_rail(
    out: AIAssessmentOut, citables: frozenset[str], flag_codes: frozenset[str] | None
) -> AIAssessmentOut:
    """Check a model answer, raising `ModelRetry` with a precise message when it is unusable.

    Citation ids match exactly: never case-folded or trimmed.
    """
    cites = [c for claim in out.claims for c in claim.cites] + [
        c for flag in out.flags for c in flag.cites
    ]
    unknown = sorted({c for c in cites if c not in citables})
    if unknown:
        raise ModelRetry(f"Unknown citation ids: {unknown}. Valid ids: {sorted(citables)}")
    if flag_codes is not None:
        bad = sorted({f.code for f in out.flags if f.code not in flag_codes})
        if bad:
            raise ModelRetry(f"Unknown flag codes: {bad}. Valid codes: {sorted(flag_codes)}")
    if out.status == "ok" and (out.stance is None or out.conviction is None):
        raise ModelRetry("An 'ok' answer needs both stance and conviction.")
    if any(not claim.cites for claim in out.claims):  # also enforced by the schema
        raise ModelRetry("Every claim needs at least one citation.")
    return out


class AINode(LensNode):
    """A lens that asks an LLM to judge, then enforces the guard rails on its answer.

    Subclasses set `prompt` (a Jinja2 template file, rendered as the static system prompt),
    optionally `variants` (named alternative templates, chosen with the `variant` param) and
    `flag_codes` (the closed list of flag codes the model may raise, if any). The model and
    settings come from the model profile named by `profile`, looked up in
    `ctx.services["profiles"]` (default: a plain `ProfileRegistry()`).

    `glossary` names the domain's glossary directory. The lens's data dictionary (the prompt
    note of every entry covering a field it sees, plus `glossary_concepts`) is derived from its
    inputs' output contracts in `bind_upstream`, which `build_plan` calls; a field without an
    entry fails the plan. The block is appended to the system prompt, after the template.
    `use_glossary=False` omits it (ablation only). See core.md, Glossary.
    """

    prompt: ClassVar[Path]
    variants: ClassVar[dict[str, Path]] = {}
    flag_codes: ClassVar[frozenset[str] | None] = None
    glossary: ClassVar[Path | None] = None  # glossary directory; loaded in bind_upstream, never at import
    glossary_concepts: ClassVar[frozenset[str]] = frozenset()  # extra ids for non-field concepts the prompt uses
    resource = "llm"

    profile: str = "dev"  # model profile name; see llm.py
    variant: str = "default"  # "default" (the `prompt`) or a key of `variants`; else rejected
    use_glossary: bool = True  # include the data dictionary in the prompt; False is for ablation only

    _bound: bool = PrivateAttr(default=False)
    _dictionary: str = PrivateAttr(default="")  # the rendered block, "" when there are no terms
    _terms: list[str] = PrivateAttr(default_factory=list)  # ids in the block, sorted

    @model_validator(mode="after")
    def _check_variant(self) -> Self:
        """Reject a variant name that is neither "default" nor declared, so typos fail loudly."""
        if self.variant != "default" and self.variant not in type(self).variants:
            raise ValueError(
                f"unknown variant {self.variant!r}; known: {['default', *type(self).variants]}"
            )
        return self

    def _template_path(self) -> Path:
        return self.variants.get(self.variant, self.prompt)

    def bind_upstream(self, outputs: Mapping[str, Any]) -> None:
        """Derive the data dictionary from the inputs' output contracts (core.md, Glossary).

        Loads the glossary, resolves every field of every input (required and optional) to an
        entry and raises `GlossaryError` naming this lens, the input and the field when one has
        none; unknown `glossary_concepts` raise too. Runs even when `use_glossary` is off, so
        coverage is still checked; the block depends on classes only, never on values.
        """
        self._bound = True
        if self.glossary is None:
            return
        glossary = Glossary.load(self.glossary)
        unknown = sorted(self.glossary_concepts - set(glossary.entries))
        if unknown:
            raise GlossaryError(f"{self.name}: unknown glossary_concepts ids: {unknown}")
        paths: dict[str, list[str]] = {}
        for input_name, output in outputs.items():
            model = contract_model(output)
            if model is None:
                continue
            for field in model_fields(model):
                term = glossary.term_for(model, field)
                if term is None:
                    raise GlossaryError(
                        f"{self.name}: input {input_name!r} field {field!r} ({model.__name__}) "
                        "has no glossary entry"
                    )
                paths.setdefault(term, []).append(f"{input_name}.{field}")
        terms = sorted({*paths, *self.glossary_concepts})
        if terms:
            self._dictionary = glossary.dictionary_block(paths, self.glossary_concepts)
            self._terms = terms

    def _check_bound(self) -> None:
        """An AI node with a glossary must have been through `build_plan`, else its prompt is incomplete."""
        if self.glossary is not None and not self._bound:
            raise GlossaryError(f"{self.name}: glossary not bound; build the node through build_plan")

    def _prompt_hash(self) -> str:
        """Hash of the rendered system prompt, so an edit to a used glossary entry changes it."""
        return content_hash(self._system_prompt())

    def memo_salt(self, services: Mapping[str, Any]) -> str:
        """Profile fingerprint plus rendered-prompt hash; see core.md, Memoization (AI nodes)."""
        registry = _registry(services)
        return content_hash([registry.fingerprint(self.profile), self._prompt_hash()])

    def _system_prompt(self) -> str:
        """The static system prompt: the rendered template, then the data dictionary unless ablated."""
        self._check_bound()
        template = _JINJA.from_string(self._template_path().read_text())
        codes = sorted(self.flag_codes) if self.flag_codes is not None else None
        prompt = template.render(lens=self.lens_name, flag_codes=codes)
        if self.use_glossary and self._dictionary:
            prompt = f"{prompt.rstrip()}\n\n{self._dictionary}"
        return prompt

    def _depth_notes(self, inputs: Mapping[str, Any]) -> dict[str, str]:
        return {
            name: f"{name}: {len(inputs[name])} of {req.desired} desired items"
            for name, req in self.depth.items()
            if name in inputs
            and not isinstance(inputs[name], Absent)
            and hasattr(inputs[name], "__len__")
        }

    async def assess(  # type: ignore[override]
        self, ctx: NodeContext, citables: frozenset[str], **inputs: Any
    ) -> LensAssessment:
        """One sampled model run, guard-railed; exhausted retries propagate and fail the node."""
        registry = _registry(ctx.services)
        usable = citables - unavailable_inputs(inputs)
        user_message = render_context(inputs, self._depth_notes(inputs))
        return await self._sample(registry, usable, user_message)

    async def _sample(
        self, registry: ProfileRegistry, citables: frozenset[str], user_message: str
    ) -> LensAssessment:
        """A single model call: one run is one call, so repeated sampling can wrap it."""
        out, extra = await call_structured(
            registry=registry,
            profile_name=self.profile,
            output_type=AIAssessmentOut,
            system_prompt=self._system_prompt(),
            user_message=user_message,
            validate=lambda out: guard_rail(out, citables, self.flag_codes),
        )
        return LensAssessment(
            status=out.status,
            stance=out.stance,
            conviction=out.conviction,
            claims=out.claims,
            flags=out.flags,
            abstain_reason=out.abstain_reason,
            provenance_extra={
                "model": extra["model"],
                "model_settings": extra["model_settings"],
                "prompt_hash": self._prompt_hash(),
                "glossary_terms": self._terms if self.use_glossary else [],
                "variant": self.variant,
                "attempts": extra["attempts"],
                "input_tokens": extra["input_tokens"],
                "output_tokens": extra["output_tokens"],
            },
        )


def _registry(services: Mapping[str, Any]) -> ProfileRegistry:
    """The injected `ProfileRegistry`, else the defaults."""
    return services.get("profiles") or ProfileRegistry()
