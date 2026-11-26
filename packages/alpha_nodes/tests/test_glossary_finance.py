"""The finance glossary: every field an AI lens sees resolves to one valid entry (TASK-64)."""

import inspect
import re
from pathlib import Path

import pytest
from alpha_nodes import metrics
from alpha_nodes.glossary import FINANCE_GLOSSARY_DIR
from alpha_nodes.lenses.price_vs_fundamentals import PriceVsFundamentals
from alpha_nodes.lenses.quality_value import QualityValue
from alpha_nodes.nodes.fetch import FxRates, Prices, Profile
from alpha_nodes.registry import build_registry
from lensgraph.ai import AINode
from lensgraph.glossary import Glossary, contract_model, model_fields
from pydantic import BaseModel

from .ai_lens_helpers import lens_input_contracts

PROMPTS = Path(metrics.__file__).parent / "prompts"
WHOLE_MODEL_OK = {"PriceWindow", "PeriodWindow", "ProfileSchema"}


@pytest.fixture(scope="module")
def glossary() -> Glossary:
    return Glossary.load(FINANCE_GLOSSARY_DIR)


def result_models() -> list[type[BaseModel]]:
    """Every pydantic model defined in alpha_nodes.metrics (windows, results and the news item)."""
    return [
        m for _, m in inspect.getmembers(metrics, inspect.isclass)
        if issubclass(m, BaseModel) and m.__module__ == metrics.__name__
    ]


def registry_outputs() -> dict[str, object]:
    """Output contract of every node in the real finance registry."""
    registry = build_registry()
    return {name: registry.get(name).output for name in registry.names() if hasattr(registry.get(name), "output")}


def lens_contracts() -> dict[str, dict[str, object]]:
    """Input contracts of each AI lens; see `lens_input_contracts` for the stand-ins."""
    return {cls.name: lens_input_contracts(cls) for cls in (QualityValue, PriceVsFundamentals)}


def test_finance_glossary_loads(glossary: Glossary) -> None:
    assert 40 <= len(glossary.entries) <= 60
    assert all(e.status == "draft" for e in glossary.entries.values())


def test_every_result_field_has_one_entry(glossary: Glossary) -> None:
    missing = [
        f"{m.__name__}.{f}" for m in result_models() if m is not metrics.NewsItem
        for f in model_fields(m) if glossary.term_for(m, f) is None
    ]
    assert missing == []


@pytest.mark.parametrize("lens_cls", [QualityValue, PriceVsFundamentals])
def test_ai_lens_plans_build(lens_cls: type[AINode]) -> None:
    lens = lens_cls()
    lens.bind_upstream(lens_input_contracts(lens_cls))  # raises GlossaryError naming any uncovered field
    # no public accessor of the bound dictionary exists, so check the private one
    assert lens._dictionary.startswith("## Data dictionary")
    assert "## Data dictionary" in lens._system_prompt()


def test_ai_lenses_declare_no_terms() -> None:
    for lens in (QualityValue, PriceVsFundamentals):
        assert lens.glossary == FINANCE_GLOSSARY_DIR
        assert lens.glossary_concepts == frozenset()


def test_no_unresolved_claims(glossary: Glossary) -> None:
    outputs = [m for o in registry_outputs().values() if (m := contract_model(o)) is not None]
    stale = glossary.unresolved_claims([*outputs, *result_models(), *lens_models()])
    assert stale == []


def lens_models() -> list[type]:
    """Frame models behind the lens inputs that no registered node produces yet."""
    return [m for c in lens_contracts().values() for o in c.values() if (m := contract_model(o)) is not None]


def test_implemented_by_resolves(glossary: Glossary) -> None:
    assert glossary.check_imports() == []


def test_no_whole_model_claim_on_metric_models(glossary: Glossary) -> None:
    whole = {claim for e in glossary.entries.values() for claim in e.fields if "." not in claim}
    assert whole == WHOLE_MODEL_OK


def test_prompt_notes_have_no_formulas(glossary: Glossary) -> None:
    bad = [
        e.id for e in glossary.entries.values()
        if "=" in e.prompt_note or re.search(r" [+*/] ", e.prompt_note)
    ]
    assert bad == []


def test_prompts_do_not_define_field_periods() -> None:
    for path in PROMPTS.glob("*.md.j2"):
        text = path.read_text()
        assert "come from an older period" not in text, path.name
        if "field_periods" in text:
            assert "Weigh fields listed in `field_periods` less" in text, path.name


def test_fetch_nodes_declare_frame_schema() -> None:
    from alpha_nodes.datasets import DATASETS
    from alpha_nodes.nodes import fetch

    nodes = [Prices, Profile, FxRates, fetch.Fundamentals, fetch.News]
    assert {n.dataset for n in nodes} == set(DATASETS)
    for node in nodes:
        assert node.contract() is DATASETS[node.dataset].frame_schema
