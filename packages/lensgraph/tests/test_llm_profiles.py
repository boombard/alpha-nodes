"""Model profiles: defaults, local-model env resolution, overrides and fingerprints."""

import pytest
from lensgraph.llm import DEFAULT_PROFILES, LLMProfile, ProfileRegistry, UsageCaps
from toy.safety_lens import SafetyLens


def test_dev_profile_is_default_and_cheapest():
    assert SafetyLens().profile == "dev"
    assert DEFAULT_PROFILES["dev"].model == "anthropic:claude-haiku-5-5"
    assert DEFAULT_PROFILES["dev"].settings == {"thinking": "low"}


def test_quality_profile_uses_sonnet_with_medium_thinking():
    quality = DEFAULT_PROFILES["quality"]
    assert quality.model == "anthropic:claude-sonnet-5-5"
    assert quality.settings == {"thinking": "medium"}


def test_local_profile_requires_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LENSGRAPH_LOCAL_MODEL", raising=False)
    registry = ProfileRegistry()
    with pytest.raises(ValueError, match="LENSGRAPH_LOCAL_MODEL"):
        registry.get("local")
    monkeypatch.setenv("LENSGRAPH_LOCAL_MODEL", "ollama:qwen3:8b")
    local = registry.get("local")
    assert local.model == "ollama:qwen3:8b"
    assert local.output_mode == "prompted"
    assert registry.model_for("local") == "ollama:qwen3:8b"


def test_unknown_profile_raises_keyerror_listing_known_names():
    with pytest.raises(KeyError, match="dev"):
        ProfileRegistry().get("nope")


def test_model_override_wins_over_model_string():
    sentinel = object()
    registry = ProfileRegistry(model_overrides={"dev": sentinel})
    assert registry.model_for("dev") is sentinel
    assert ProfileRegistry().model_for("dev") == "anthropic:claude-haiku-5-5"


def test_override_does_not_need_local_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LENSGRAPH_LOCAL_MODEL", raising=False)
    registry = ProfileRegistry(model_overrides={"local": object()})
    assert registry.model_for("local") is not None
    assert registry.fingerprint("local")


def test_custom_profiles_replace_defaults():
    profile = LLMProfile(name="x", model="test")
    registry = ProfileRegistry({"x": profile})
    assert registry.get("x") is profile
    with pytest.raises(KeyError):
        registry.get("dev")


def _fp(**kwargs) -> str:
    profile = LLMProfile(name="t", model="m", **kwargs)
    return ProfileRegistry({"t": profile}).fingerprint("t")


def test_fingerprint_is_stable_and_sensitive_to_settings_and_output_mode():
    assert _fp() == _fp()
    assert _fp(settings={"thinking": "low"}) != _fp(settings={"thinking": "high"})
    assert _fp(output_mode="tool") != _fp(output_mode="prompted")


def test_fingerprint_differs_by_model_id_and_override_type():
    profile = LLMProfile(name="t", model="m")
    other = LLMProfile(name="t", model="n")
    assert ProfileRegistry({"t": profile}).fingerprint("t") != ProfileRegistry({"t": other}).fingerprint("t")
    overridden = ProfileRegistry({"t": profile}, model_overrides={"t": object()})
    assert overridden.fingerprint("t") != ProfileRegistry({"t": profile}).fingerprint("t")


def test_default_usage_limits():
    for name in ("dev", "quality"):
        profile = DEFAULT_PROFILES[name]
        assert profile.usage_limits == UsageCaps(
            request_limit=profile.max_retries + 2, total_tokens_limit=50_000
        )
    local = DEFAULT_PROFILES["local"].usage_limits
    assert local == UsageCaps(request_limit=DEFAULT_PROFILES["local"].max_retries + 2)


def test_changing_usage_limits_changes_fingerprint():
    base = _fp(usage_limits=UsageCaps(request_limit=3))
    assert base == _fp(usage_limits=UsageCaps(request_limit=3))
    assert base != _fp(usage_limits=UsageCaps(request_limit=4))
    assert base != _fp(usage_limits=UsageCaps(request_limit=3, total_tokens_limit=10))
    assert base != _fp()


def test_usage_caps_convert_to_pydantic_ai_limits():
    limits = UsageCaps(request_limit=3, output_tokens_limit=7).to_limits()
    assert (limits.request_limit, limits.output_tokens_limit, limits.input_tokens_limit) == (3, 7, None)
