"""Model profiles: named, fingerprintable bundles of model id, settings and output mode.

See documentation/design/core.md, AI nodes (guard rails), Model profiles. AI nodes look their
profile up in a `ProfileRegistry` passed as `services["profiles"]`; the profile's fingerprint
is part of the AI node's memo key (`AINode.memo_salt`).
"""

import os
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai.usage import UsageLimits

from .hashing import content_hash

_ENV_PREFIX = "env:"


class UsageCaps(BaseModel):
    """Per-call ceilings on model requests and tokens; converts to pydantic-ai `UsageLimits`.

    A small frozen model rather than `UsageLimits` itself, so a profile stays pydantic-first,
    frozen and hashable by `ProfileRegistry.fingerprint`. `None` means no ceiling.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_limit: int | None = None
    input_tokens_limit: int | None = None
    output_tokens_limit: int | None = None
    total_tokens_limit: int | None = None

    def to_limits(self) -> UsageLimits:
        """The equivalent pydantic-ai `UsageLimits`."""
        return UsageLimits(**self.model_dump())


class LLMProfile(BaseModel):
    """One named way of calling an LLM: which model, with which settings, in which output mode.

    Args:
        name: the profile name nodes select, e.g. `dev`.
        model: a pydantic-ai model string (`anthropic:claude-haiku-5-5`), or `env:VAR` to read
            the model string from environment variable `VAR` when the profile is resolved.
        settings: pydantic-ai `ModelSettings` (e.g. `{"thinking": "low"}`).
        output_mode: how the structured answer is requested. `tool` suits API models;
            `prompted` suits local models with weak tool calling.
        max_retries: how often the guard rail may send the model back to fix its answer.
        usage_limits: ceilings for one call (all its retries). Exceeding one raises
            pydantic-ai's `UsageLimitExceeded`, which fails the node; there is no fallback.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    model: str
    settings: dict[str, Any] = {}
    output_mode: Literal["tool", "native", "prompted"] = "tool"
    max_retries: int = 2
    usage_limits: UsageCaps | None = None


LOCAL_MODEL_ENV = "LENSGRAPH_LOCAL_MODEL"
"""Environment variable naming the local (Ollama) model, e.g. `ollama:qwen3:8b`."""

def _caps(retries: int, tokens: int | None = None) -> UsageCaps:
    """Default ceilings: the first request plus `max_retries` (2) retries and one spare."""
    return UsageCaps(request_limit=retries + 2, total_tokens_limit=tokens)


DEFAULT_PROFILES: dict[str, LLMProfile] = {
    "dev": LLMProfile(
        name="dev",
        model="anthropic:claude-haiku-5-5",
        settings={"thinking": "low"},
        usage_limits=_caps(2, tokens=50_000),
    ),
    "quality": LLMProfile(
        name="quality",
        model="anthropic:claude-sonnet-5-5",
        settings={"thinking": "medium"},
        usage_limits=_caps(2, tokens=50_000),
    ),
    "local": LLMProfile(
        name="local",
        model=f"{_ENV_PREFIX}{LOCAL_MODEL_ENV}",
        output_mode="prompted",
        usage_limits=_caps(2),
    ),
}
"""Built-in profiles. `dev` is the cheapest and the default everywhere."""


def _env_model(var: str) -> str | None:
    """The model string named by `var`; the local model is read through `Settings`."""
    if var == LOCAL_MODEL_ENV:
        from .config import Settings  # lazy: config imports run, which imports the AI nodes

        return Settings().local_model
    return os.environ.get(var)


def describe_model(model: Any) -> str:
    """A human-readable id for a model string or a pydantic-ai `Model` instance (provenance)."""
    if isinstance(model, str):
        return model
    return str(getattr(model, "model_name", type(model).__qualname__))


class ProfileRegistry:
    """Looks up profiles by name and resolves them to models; tests inject model instances.

    Args:
        profiles: replaces `DEFAULT_PROFILES` entirely when given.
        model_overrides: profile name -> pydantic-ai `Model` instance used instead of the
            profile's model string (how tests plug in `FunctionModel`/`TestModel`).
    """

    def __init__(
        self,
        profiles: Mapping[str, LLMProfile] | None = None,
        model_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        self._profiles = dict(DEFAULT_PROFILES if profiles is None else profiles)
        self._overrides = dict(model_overrides or {})

    def get(self, name: str) -> LLMProfile:
        """The profile `name`, with any `env:VAR` model resolved.

        Raises `KeyError` for an unknown name and `ValueError` naming the variable when an
        `env:` model is unset (and no override stands in for it).
        """
        try:
            profile = self._profiles[name]
        except KeyError:
            raise KeyError(f"unknown model profile {name!r}; known: {sorted(self._profiles)}") from None
        if profile.model.startswith(_ENV_PREFIX) and name not in self._overrides:
            var = profile.model.removeprefix(_ENV_PREFIX)
            value = _env_model(var)
            if not value:
                raise ValueError(f"profile {name!r} needs a model: set environment variable {var}")
            return profile.model_copy(update={"model": value})
        return profile

    def model_for(self, name: str) -> Any:
        """The override instance for `name` if any, else the profile's model string."""
        if name in self._overrides:
            return self._overrides[name]
        return self.get(name).model

    def fingerprint(self, name: str) -> str:
        """Hash of what changes a call's behaviour: model id (or override type), settings, mode, limits."""
        profile = self.get(name)
        if name in self._overrides:
            model_id = f"override:{type(self._overrides[name]).__qualname__}"
        else:
            model_id = profile.model
        return content_hash([model_id, profile.settings, profile.output_mode, profile.usage_limits])
