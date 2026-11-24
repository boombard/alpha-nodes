"""Citation lineage: every cite in a verdict resolves to a stored value via its provenance."""

import pandas as pd
import pytest
from lensgraph.lineage import UnresolvedCitation, resolve_all, resolve_citation
from lensgraph.plan import NodeKey
from lensgraph.store.files import FileBlobStore
from lensgraph.store.memory import InMemoryBlobStore
from lensgraph.verdict import Claim, Flag, LensVerdict, Provenance
from toy.nodes import ToxNote


def _verdict(hashes: dict[str, str], cites: list[str], flag_cites: list[str] | None = None) -> LensVerdict:
    return LensVerdict(
        lens="t",
        status="ok",
        stance=1,
        conviction="low",
        stance_mean=1.0,
        coverage=1.0,
        claims=[Claim(text="c", direction=1, cites=cites)],
        flags=[Flag(severity="info", code="x", text="x", cites=flag_cites)] if flag_cites else [],
        provenance=Provenance(lens_version="v", input_hashes=hashes),
    )


@pytest.fixture
def blobs() -> InMemoryBlobStore:
    return InMemoryBlobStore()


def test_resolve_node_level_frame(blobs):
    h = blobs.put(pd.DataFrame({"a": [1, 2]}))
    got = resolve_citation(_verdict({"df": h}, ["df"]), "df", blobs)
    assert got.kind == "frame" and got.source_hash == h and got.cite == "df"
    assert got.value["a"].tolist() == [1, 2]


def test_resolve_node_level_scalar_and_model(blobs):
    h_val, h_model = blobs.put(0.25), blobs.put(ToxNote(id="n", text="t"))
    v = _verdict({"growth_rate": h_val, "note": h_model}, ["growth_rate", "note"])
    assert resolve_citation(v, "growth_rate", blobs).kind == "value"
    assert resolve_citation(v, "growth_rate", blobs).value == 0.25
    assert resolve_citation(v, "note", blobs).kind == "model"


def test_resolve_list_item_by_id(blobs):
    notes = [ToxNote(id="S1-n1", text="a"), ToxNote(id="S1-n2", text="b")]
    v = _verdict({"tox_notes": blobs.put(notes)}, ["tox_notes[S1-n2]"])
    got = resolve_citation(v, "tox_notes[S1-n2]", blobs)
    assert got.kind == "item" and got.value == notes[1]


def test_resolve_model_field(blobs):
    v = _verdict({"note": blobs.put(ToxNote(id="n", text="hello"))}, ["note.text"])
    got = resolve_citation(v, "note.text", blobs)
    assert got.kind == "field" and got.value == "hello"


def test_resolve_all_covers_claims_and_flags(blobs):
    h = blobs.put(1.0)
    v = _verdict({"a": h, "b": h}, ["a"], flag_cites=["b"])
    assert set(resolve_all(v, blobs)) == {"a", "b"}


@pytest.mark.parametrize(
    "cite", ["nope", "tox_notes[missing]", "tox_notes.field", "gone", "note.nofield"]
)
def test_unresolved_citation_names_cite(blobs, cite):
    v = _verdict(
        {
            "tox_notes": blobs.put([ToxNote(id="S1-n1", text="a")]),
            "gone": "0" * 64,  # hash with no blob
            "note": blobs.put(ToxNote(id="n", text="t")),
        },
        [cite],
    )
    with pytest.raises(UnresolvedCitation, match=cite.replace("[", r"\[").replace(".", r"\.")):
        resolve_citation(v, cite, blobs)


def test_resolve_after_cache_hit(toy_panel_runner, tmp_path):
    toy_panel_runner()
    second = toy_panel_runner()
    verdict = second.values[NodeKey(name="safety_lens", candidate="S1")]
    assert second.results[NodeKey(name="safety_lens", candidate="S1")].cache_hit
    resolved = resolve_all(verdict, FileBlobStore(tmp_path / "blobs"))
    assert isinstance(resolved["growth_rate"].value, float)
    assert resolved["tox_notes[S1-n1]"].kind == "item"
