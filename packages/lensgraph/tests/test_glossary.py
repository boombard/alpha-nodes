"""Glossary mechanism: entry model, loader validation, prompt block and export (core.md, Glossary)."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from lensgraph.glossary import Glossary, GlossaryError

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
    assert glossary.by_field() == {
        "GrowthResult.rate": "growth-rate",
        "GrowthResult.doubling_hours": "doubling-time",
    }


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


def test_prompt_block_sorted_and_stable():
    glossary = Glossary.load(TOY)
    block = glossary.prompt_block(["toxicity-note", "growth-rate"])
    assert block == glossary.prompt_block(["growth-rate", "toxicity-note"])
    assert block.startswith("## Terms\n")
    assert block.index("**Growth rate (GR)**") < block.index("**Toxicity note (TN)**")
    assert "**Doubling time**: Hours to double." not in block  # not selected
    assert "**Doubling time**: Hours to double." in glossary.prompt_block(["doubling-time"])


def test_prompt_block_unknown_id_rejected():
    with pytest.raises(GlossaryError, match="nope"):
        Glossary.load(TOY).prompt_block(["nope"])


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


def test_prompt_block_unescapes_dollar(edit):
    glossary = Glossary.load(edit("toxicity-note", "A single observation", r"Worth \$5. A single observation"))
    assert r"\$5" in glossary.entries["toxicity-note"].prompt_note  # stored verbatim
    block = glossary.prompt_block(["toxicity-note"])
    assert "Worth $5." in block and "\\$" not in block
