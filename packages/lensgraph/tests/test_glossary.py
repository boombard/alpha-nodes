"""Glossary mechanism: entry model, loader validation, prompt block and export (core.md, Glossary)."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pandera.pandas as pa
import pytest
from lensgraph.glossary import Glossary, GlossaryError, model_fields
from pandera.typing import Index, Series
from pydantic import BaseModel

TOY = Path(__file__).parent / "toy" / "glossary"


@pytest.fixture
def toy_dir(tmp_path: Path) -> Path:
    """A writable copy of the toy glossary."""
    target = tmp_path / "glossary"
    shutil.copytree(TOY, target)
    return target


@pytest.fixture
def edit(toy_dir: Path) -> Callable[..., Path]:
    """Factory: apply a text replacement to one toy entry file and return the directory."""

    def go(entry: str, old: str, new: str) -> Path:
        path = toy_dir / f"{entry}.md"
        text = path.read_text()
        assert old in text
        path.write_text(text.replace(old, new, 1))
        return toy_dir

    return go


def test_load_toy_glossary():
    glossary = Glossary.load(TOY)
    assert sorted(glossary.entries) == ["doubling-time", "growth-rate", "toxicity-note"]
    entry = glossary.entries["growth-rate"]
    assert entry.name == "Growth rate" and entry.abbreviations == ["GR"]
    assert entry.status == "draft" and entry.related == ["doubling-time"]
    assert glossary.entries["doubling-time"].fields == ["GrowthResult.doubling_hours"]


def test_id_must_match_stem(toy_dir):
    (toy_dir / "growth-rate.md").rename(toy_dir / "growth.md")
    with pytest.raises(GlossaryError, match=r"growth\.md.*id"):
        Glossary.load(toy_dir)


def test_missing_required_section_rejected(edit):
    directory = edit("growth-rate", "## Why it matters", "## Provider notes")
    with pytest.raises(GlossaryError, match=r"growth-rate\.md.*relevance"):
        Glossary.load(directory)


def test_unknown_related_rejected(edit):
    directory = edit("growth-rate", "related: [doubling-time]", "related: [nope]")
    with pytest.raises(GlossaryError, match=r"growth-rate\.md.*nope"):
        Glossary.load(directory)


def test_verified_needs_sources(edit):
    directory = edit("doubling-time", "sources: [lab-handbook]", "sources: []")
    with pytest.raises(GlossaryError, match=r"doubling-time\.md.*sources"):
        Glossary.load(directory)


def test_field_claimed_twice_rejected(edit):
    directory = edit("toxicity-note", "fields: []", "fields: [GrowthResult.rate]")
    with pytest.raises(GlossaryError, match=r"GrowthResult\.rate"):
        Glossary.load(directory)


def test_prompt_note_length_capped(edit):
    directory = edit(
        "toxicity-note",
        "A single observation, not a rate. Weigh the wording.",
        " ".join(["word"] * 61),
    )
    with pytest.raises(GlossaryError, match=r"toxicity-note\.md.*prompt note"):
        Glossary.load(directory)


def test_prompt_note_with_math_rejected(edit):
    directory = edit("toxicity-note", "A single observation", "Compute $a+b$. A single observation")
    with pytest.raises(GlossaryError, match=r"toxicity-note\.md.*formula"):
        Glossary.load(directory)


def test_check_imports_reports_unresolved(edit):
    assert Glossary.load(TOY).check_imports() == []
    directory = edit("growth-rate", "toy.nodes.GrowthRate", "toy.nodes.Missing")
    assert Glossary.load(directory).check_imports() == ["toy.nodes.Missing"]


def test_raw_html_rejected(edit):
    directory = edit("growth-rate", "How fast", "<b>How</b> fast")
    with pytest.raises(GlossaryError, match=r"growth-rate\.md.*HTML"):
        Glossary.load(directory)


def test_html_inside_code_is_allowed(edit):
    directory = edit("growth-rate", "How fast", "Use `<b>` literally. How fast")
    Glossary.load(directory)


def test_unbalanced_math_rejected(edit):
    directory = edit("doubling-time", "for growth rate $r$.", "for growth rate $r.")
    with pytest.raises(GlossaryError, match=r"doubling-time\.md.*math"):
        Glossary.load(directory)


def test_relative_links_must_resolve(edit):
    directory = edit("doubling-time", "(growth-rate.md)", "(ghost.md)")
    with pytest.raises(GlossaryError, match=r"doubling-time\.md.*ghost"):
        Glossary.load(directory)


def test_sections_keyed_by_fixed_keys():
    sections = Glossary.load(TOY).entries["doubling-time"].sections
    assert set(sections) == {
        "definition", "calculation", "relevance", "shortcomings", "similar", "sources",
        "prompt_note",
    }
    assert sections["definition"] == "Time for the culture to double."
    assert Glossary.load(TOY).entries["doubling-time"].prompt_note == (
        "Hours to double. Smaller means faster growth."
    )


def test_export_is_stable_and_hashes_content(edit):
    first = Glossary.load(TOY).export()
    again = Glossary.load(TOY).export()
    assert first == again and first.model_dump_json() == again.model_dump_json()
    assert first.schema_version == 1
    assert [e.id for e in first.entries] == ["doubling-time", "growth-rate", "toxicity-note"]
    edited = Glossary.load(edit("toxicity-note", "Counted per strain", "Tallied per strain")).export()
    assert edited.content_hash != first.content_hash


def test_escaped_dollar_allowed(edit):
    directory = edit("growth-rate", "How fast", r"Costs \$5 per share. How fast")
    directory = edit("toxicity-note", "A single observation", r"Worth \$5. A single observation")
    glossary = Glossary.load(directory)
    assert r"\$5" in glossary.entries["toxicity-note"].prompt_note
    with pytest.raises(GlossaryError, match="formula"):
        Glossary.load(edit("toxicity-note", "Worth", "Worth $x$ and"))


def test_autolink_is_not_html(edit):
    Glossary.load(edit("growth-rate", "How fast", "See <https://example.com> and <me@example.com>. How fast"))
    with pytest.raises(GlossaryError, match="HTML"):
        Glossary.load(edit("growth-rate", "See <https", "<b>x</b> <https"))



class Window(BaseModel):
    """A metadata model claimed as a whole."""

    start: str
    end: str


class Metrics(BaseModel):
    """A model whose fields are claimed one by one."""

    rate: float
    other: float = 0.0


class Child(Metrics):
    """Inherits `rate` and `other` from `Metrics`; adds `extra`."""

    extra: float = 0.0


class SubWindow(Window):
    """Adds a metric-like field to a whole-model-claimed base."""

    extra: str = ""


class Prices(pa.DataFrameModel):
    """A pandera frame contract: columns are its fields."""

    close: float
    volume: float
    adj_close: Series[float] = pa.Field(alias="Adj Close")
    when: Index[int]


_ENTRY = """---
id: {id}
name: {name}
abbreviations: {abbr}
aliases: []
kind: {kind}
fields: {fields}
implemented_by: []
related: []
status: draft
sources: []
summary: A test term.
category: test
---

## Definition

d

## How we calculate it

c

## Why it matters

r

## Shortcomings and pitfalls

s

## Similar terms

none

## Prompt note

{note}
"""


@pytest.fixture
def glossary_of(tmp_path: Path) -> Callable[..., Glossary]:
    """Factory: write entries `id=(fields, note)` (optional `kind`, `name`, `abbr` via a dict) and load them."""

    def make(**entries: tuple[list[str], str] | dict) -> Glossary:
        directory = tmp_path / "made"
        directory.mkdir(exist_ok=True)
        for entry_id, spec in entries.items():
            if isinstance(spec, tuple):
                spec = {"fields": spec[0], "note": spec[1]}
            text = _ENTRY.format(
                id=entry_id,
                name=spec.get("name", entry_id.upper()),
                abbr=spec.get("abbr", []),
                kind=spec.get("kind", "ratio"),
                fields=spec["fields"],
                note=spec["note"],
            )
            (directory / f"{entry_id}.md").write_text(text)
        return Glossary.load(directory)

    return make


def test_term_for_exact_claim(glossary_of):
    glossary = glossary_of(a=(["Metrics.rate"], "n"), b=(["Metrics.other"], "n"))
    assert glossary.term_for(Metrics, "rate") == "a"
    assert glossary.term_for(Metrics, "other") == "b"
    assert glossary.term_for(Metrics, "missing") is None


def test_term_for_walks_mro_to_base_claim(glossary_of):
    glossary = glossary_of(a=(["Metrics.rate"], "n"))
    assert glossary.term_for(Child, "rate") == "a"  # claimed once, on the base
    assert glossary.term_for(Child, "extra") is None


def test_whole_model_claim_covers_its_fields_only(glossary_of):
    glossary = glossary_of(w=(["Window"], "n"))
    assert glossary.term_for(Window, "start") == "w"
    assert glossary.term_for(SubWindow, "end") == "w"  # inherited field: the base's claim
    assert glossary.term_for(SubWindow, "extra") is None  # declared on the subclass: not covered


def test_exact_claim_beats_whole_model_claim(glossary_of):
    glossary = glossary_of(w=(["Window"], "n"), s=(["Window.start"], "n"))
    assert glossary.term_for(Window, "start") == "s"
    assert glossary.term_for(Window, "end") == "w"


def test_frame_alias_column_resolves(glossary_of):
    glossary = glossary_of(c=(["Prices.adj_close"], "n"))
    assert model_fields(Prices) == ["adj_close", "close", "volume"]  # attribute names; no Index
    assert glossary.term_for(Prices, "adj_close") == "c"
    assert glossary.unresolved_claims([Prices]) == []


def test_frame_columns_resolve(glossary_of):
    glossary = glossary_of(c=(["Prices.close"], "n"), v=(["Prices"], "n"))
    assert glossary.term_for(Prices, "close") == "c"
    assert glossary.term_for(Prices, "volume") == "v"


@pytest.mark.parametrize("claim", ["Metrics.rate", "Window"])
def test_duplicate_claim_rejected(tmp_path, claim):
    directory = tmp_path / "dup"
    directory.mkdir()
    for entry_id in ("a", "b"):
        (directory / f"{entry_id}.md").write_text(
            _ENTRY.format(id=entry_id, name=entry_id, abbr=[], kind="x", fields=[claim], note="n")
        )
    with pytest.raises(GlossaryError, match=claim.replace(".", r"\.")):
        Glossary.load(directory)


def test_unresolved_claims_lists_stale_ones(glossary_of):
    glossary = glossary_of(
        a=(["Metrics.rate", "Metrics.gone"], "n"), b=(["Ghost"], "n"), c=(["Window", "Child.extra"], "n")
    )
    assert glossary.unresolved_claims([Metrics, Window, Child]) == ["Ghost", "Metrics.gone"]
    assert glossary.unresolved_claims([Metrics, Window]) == ["Child.extra", "Ghost", "Metrics.gone"]


def test_dictionary_block_lists_paths_kind_and_note(glossary_of):
    glossary = glossary_of(
        b={"fields": [], "note": "Note b.", "kind": "ratio", "name": "Bee", "abbr": ["B"]},
        a={"fields": [], "note": "Note a.", "kind": "money", "name": "Ay"},
        c={"fields": [], "note": "Note c.", "kind": "concept", "name": "Sea"},
    )
    block = glossary.dictionary_block({"b": ["in.y", "in.x", "other.z"], "a": ["in.q"]}, ["c"])
    assert block == (
        "## Data dictionary\n\n"
        "- in.q (money): **Ay**: Note a.\n"
        "- in.{x, y}, other.z (ratio): **Bee (B)**: Note b.\n"
        "- (concept): **Sea**: Note c.\n"
    )


def test_dictionary_block_unknown_id_rejected(glossary_of):
    with pytest.raises(GlossaryError, match="nope"):
        glossary_of(a=([], "n")).dictionary_block({"nope": ["in.x"]})


def test_dictionary_block_unescapes_dollar(glossary_of):
    glossary = glossary_of(a=([], r"Worth \$5."))
    block = glossary.dictionary_block({"a": ["in.x"]})
    assert "Worth $5." in block and "\\$" not in block
