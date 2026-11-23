"""citable_ids derivation."""

import pandas as pd
from lensgraph.citations import citable_ids
from pydantic import BaseModel


class Doc(BaseModel):
    id: str
    title: str
    year: int
    tags: list[str] = []


class NoId(BaseModel):
    text: str


def test_citable_ids_model_fields_list_items_frames():
    inputs = {
        "doc": Doc(id="d", title="T", year=3, tags=["x"]),
        "docs": [Doc(id="a", title="A", year=1), Doc(id="b", title="B", year=2)],
        "plain": [NoId(text="x")],
        "frame": pd.DataFrame({"a": [1]}),
        "num": 1.5,
    }
    assert citable_ids(inputs) == frozenset(
        {
            "doc", "doc.id", "doc.title", "doc.year",
            "docs", "docs[a]", "docs[b]",
            "plain", "frame", "num",
        }
    )
