"""Tests for run configuration: RunConfig YAML loading, load_object and Settings."""

from pathlib import Path

import pytest
from lensgraph.config import RunConfig, Settings, load_object
from pydantic import ValidationError

TOY_YAML = Path(__file__).parent / "toy" / "toy_run.yaml"


def test_run_config_from_yaml_roundtrip():
    cfg = RunConfig.from_yaml(TOY_YAML)
    assert cfg.targets == []
    assert cfg.panel is not None and cfg.panel.lenses == ["growth_lens", "safety_lens"]
    assert [c.id for c in cfg.candidates] == ["S1", "S2", "S3"]
    assert cfg.nodes["safety_lens"]["profile"] == "test"
    assert cfg.brief is not None and cfg.report.enabled
    assert RunConfig.model_validate(cfg.model_dump(mode="json")) == cfg


def test_toy_registry_and_services_resolve_from_config():
    cfg = RunConfig.from_yaml(TOY_YAML)
    registry = load_object(cfg.registry)
    assert "growth_lens" in registry.names() and "safety_lens" in registry.names()
    assert cfg.services is not None and {"assays", "profiles"} <= set(load_object(cfg.services))


@pytest.mark.parametrize(
    ("extra", "key"),
    [("bogus_key: 1\n", "bogus_key"), ("report_typo: 1\n", "report_typo")],
)
def test_unknown_key_rejected_top_level(tmp_path, extra, key):
    path = tmp_path / "run.yaml"
    path.write_text(TOY_YAML.read_text() + extra)
    with pytest.raises(ValidationError, match=key):
        RunConfig.from_yaml(path)


def test_unknown_report_key_rejected(tmp_path):
    path = tmp_path / "run.yaml"
    path.write_text(TOY_YAML.read_text() + "report:\n  max_rowz: 3\n")
    with pytest.raises(ValidationError, match="max_rowz"):
        RunConfig.from_yaml(path)


def test_load_object_factory_and_attr():
    assert load_object("toy.registry:build_services")["assays"] is not None
    assert load_object("pathlib:Path") is Path  # classes are returned, not instantiated
    assert load_object("os.path:sep") == "/"
    with pytest.raises(ImportError, match="no_such_mod:x"):
        load_object("no_such_mod:x")
    with pytest.raises(AttributeError, match="os.path:nope"):
        load_object("os.path:nope")


def test_settings_env_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv("LENSGRAPH_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("LENSGRAPH_LOCAL_MODEL", "ollama:x")
    settings = Settings()
    assert settings.store_root == tmp_path and settings.local_model == "ollama:x"
