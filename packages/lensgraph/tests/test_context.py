"""render_context: how node outputs become citable blocks in an AI lens prompt."""

import pandas as pd
import pytest
from lensgraph.citations import citable_ids
from lensgraph.context import render_context, unavailable_inputs
from lensgraph.types import Absent
from toy.nodes import ToxNote


def test_render_context_frame_truncation():
    frame = pd.DataFrame({"t": range(100), "v": [x * 2 for x in range(100)]})
    text = render_context({"assay": frame}, max_rows=5)
    assert "### [assay]" in text
    assert "(showing last 5 of 100 rows)" in text
    assert "99,198" in text and "95,190" in text
    assert "94,188" not in text


def test_render_context_small_frame_has_no_truncation_note():
    assert "showing last" not in render_context({"assay": pd.DataFrame({"t": [1, 2]})})


def test_render_context_absent_input_is_not_available_and_not_citable():
    inputs = {"growth_rate": 0.5, "tox_notes": Absent(reason="upstream 'tox_notes' failed: boom")}
    text = render_context(inputs)
    assert "### tox_notes: NOT AVAILABLE (upstream 'tox_notes' failed: boom)" in text
    assert "### [tox_notes]" not in text
    assert unavailable_inputs(inputs) == {"tox_notes"}


def test_render_context_empty_list_is_not_available():
    assert unavailable_inputs({"tox_notes": [], "growth_rate": 1.0}) == {"tox_notes"}
    assert "### tox_notes: NOT AVAILABLE" in render_context({"tox_notes": []})


def test_render_context_list_items_one_block_each_ordered_by_input_name():
    notes = [ToxNote(id="a", text="first"), ToxNote(id="b", text="second")]
    text = render_context({"tox_notes": notes, "growth_rate": 0.25})
    assert text.index("### [growth_rate]") < text.index("### [tox_notes]")
    assert text.index("### [tox_notes[a]]") < text.index("### [tox_notes[b]]")
    assert '"text":"first"' in text


def test_render_context_model_renders_one_block_per_field_id():
    text = render_context({"note": ToxNote(id="a", text="hello")})
    assert "### [note]" in text and "### [note.id]" in text and "### [note.text]" in text


def test_every_citable_id_has_a_block():
    inputs = {
        "growth_rate": 0.5,
        "tox_notes": [ToxNote(id="n1", text="x"), ToxNote(id="n2", text="y")],
        "note": ToxNote(id="z", text="w"),
        "frame": pd.DataFrame({"a": [1]}),
    }
    text = render_context(inputs)
    for cid in citable_ids(inputs):
        assert f"### [{cid}]" in text


def test_render_context_depth_notes_are_appended():
    text = render_context({"growth_rate": 1.0}, {"tox_notes": "tox_notes: 1 of 3 desired items"})
    assert "tox_notes: 1 of 3 desired items" in text


@pytest.mark.parametrize("value", [1.5, "plain text", [1, 2, 3]])
def test_render_context_plain_values(value):
    assert "### [x]" in render_context({"x": value})


def _culture_units():
    from lensgraph.units import unit_of
    from toy.unit_models import Culture

    return {f"culture.{f}": u for f in Culture.model_fields if (u := unit_of(Culture, f))}


def test_evidence_formats_unit_fields():
    from toy.unit_models import Culture

    culture = Culture(yield_frac=0.153, doubling=3.5, fold=2.0, volume=12_300_000, vessel="L")
    text = render_context({"culture": culture}, units=_culture_units())
    assert '"yield_frac": "15.3%"' in text
    assert '"doubling": "3.5 h"' in text
    assert '"volume": "L 12.3m"' in text  # prefix_field read from the sibling field
    assert '"stable": true' in text and '"vessel": "L"' in text
    assert "### [culture.yield_frac]\n\"15.3%\"" in text
    assert "0.153" not in text


def test_evidence_without_units_is_raw():
    from toy.unit_models import Culture

    assert "0.153" in render_context({"culture": Culture(yield_frac=0.153)})


def test_none_unit_field_stays_null():
    from toy.unit_models import Culture

    text = render_context({"culture": Culture()}, units=_culture_units())
    assert '"yield_frac": null' in text


def test_frame_cells_formatted_headers_unchanged():
    from lensgraph.units import FRACTION

    frame = pd.DataFrame({"ret": [0.05, -0.0004], "label": ["a", "b"]})
    text = render_context({"px": frame}, units={"px.ret": FRACTION})
    assert text.splitlines()[1] == "ret,label"
    assert "5%,a" in text and "-0.04%,b" in text
    assert "0.05" not in text
    assert frame["ret"].tolist() == [0.05, -0.0004]  # the input frame is not mutated


def test_list_items_without_ids_are_formatted():
    import json

    from lensgraph.units import FRACTION
    from pydantic import BaseModel

    class Row(BaseModel):
        ret: float

    text = render_context({"rows": [Row(ret=0.05), Row(ret=0.1)]}, units={"rows.ret": FRACTION})
    assert json.loads(text.split("\n", 1)[1]) == [{"ret": "5%"}, {"ret": "10%"}]
