import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from lensgraph.hashing import content_hash, memo_key
from lensgraph.types import Absent
from pydantic import BaseModel
from toy.nodes import AssayRaw, GrowthRate, ToxNote


def test_frame_hash_stable_and_order_sensitive():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    assert content_hash(df) == content_hash(df.copy())
    assert content_hash(df) != content_hash(df.iloc[::-1])
    assert content_hash(df) != content_hash(df.astype("float32"))


def test_model_hash_includes_type():
    class Other(BaseModel):
        id: str
        text: str

    assert content_hash(ToxNote(id="a", text="b")) != content_hash(Other(id="a", text="b"))


def test_dict_key_order_irrelevant():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})
    assert content_hash([1, 2]) != content_hash([2, 1])


def test_none_vs_absent_differ():
    assert content_hash(None) != content_hash(Absent(reason="r"))


def test_nan_hashes_stably():
    assert content_hash(float("nan")) == content_hash(np.nan)


def test_memo_key_changes_with_params_inputs_candidate_salt():
    base = memo_key(GrowthRate(), {"assay": "h1"}, "S1")
    assert base == memo_key(GrowthRate(), {"assay": "h1"}, "S1")
    assert base != memo_key(GrowthRate(window=9), {"assay": "h1"}, "S1")
    assert base != memo_key(GrowthRate(), {"assay": "h2"}, "S1")
    assert base != memo_key(GrowthRate(), {"assay": "h1"}, "S2")
    assert base != memo_key(GrowthRate(), {"assay": "h1"}, "S1", salt="x")


def test_memo_key_fetch_ignores_source():
    class AssayRaw2(AssayRaw):
        def run(self, ctx):
            return None

    assert memo_key(AssayRaw(), {}, "S1") == memo_key(AssayRaw2(), {}, "S1")


def test_long_arrays_differing_in_middle_hash_differently():
    a = np.zeros(10_000)
    b = a.copy()
    b[5_000] = 1.0
    assert content_hash(a) != content_hash(b)
    assert content_hash(a) == content_hash(a.copy())


def test_series_hash_order_sensitive():
    s = pd.Series([1.0, 2.0, 3.0], name="x")
    assert content_hash(s) == content_hash(s.copy())
    assert content_hash(s) != content_hash(s.iloc[::-1])


def test_date_hash_stable_and_type_tagged():
    assert content_hash(date(2026, 1, 2)) == content_hash(date(2026, 1, 2))
    assert content_hash(date(2026, 1, 2)) != content_hash(date(2026, 1, 3))
    assert content_hash(date(2026, 1, 2)) != content_hash(datetime(2026, 1, 2))
    assert content_hash(b"ab") != content_hash(b"ac")


def test_unsupported_type_raises():
    with pytest.raises(TypeError, match="unsupported type object"):
        content_hash(object())


_STABILITY_SCRIPT = """
from typing import ClassVar
from pydantic import BaseModel
from lensgraph.hashing import content_hash, memo_key
from lensgraph.node import CalcNode


class Tagged(BaseModel):
    tags: frozenset[str]


class TagNode(CalcNode):
    name: ClassVar[str] = "tag_node"
    tags: frozenset[str] = frozenset()


tags = frozenset({"alpha", "beta", "gamma", "delta", "epsilon", "zeta"})
print(content_hash(Tagged(tags=tags)))
print(memo_key(TagNode(tags=tags), {"x": "h"}, "S1"))
"""


def _hashes_under_seed(script: Path, seed: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(script)],
        env={**os.environ, "PYTHONHASHSEED": seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


def test_model_and_memo_hashes_stable_across_processes_with_set_fields(tmp_path):
    # a real file, so inspect.getsource works for the node class
    script = tmp_path / "probe.py"
    script.write_text(_STABILITY_SCRIPT)
    first, second = _hashes_under_seed(script, "1"), _hashes_under_seed(script, "2")
    assert len(first) == 2
    assert first == second


def test_frame_without_list_cells_hashes_as_before():
    """Pinned digest: frames with no list cells must keep their pre-existing hash."""
    df = pd.DataFrame({"a": [1.0, 2.0], "s": ["x", "y"]})
    assert content_hash(df) == "81d7e70e8b32a1c77261cf48b157bcd57beb623befd10d2b525fc1b10fefe6ed"


def test_list_cells_equal_numpy_array_cells():
    """A Parquet round trip turns list cells into arrays; the hash must not change."""
    as_lists = pd.DataFrame({"r": [["a", "b"], []]})
    as_arrays = pd.DataFrame({"r": [np.array(["a", "b"], dtype=object), np.array([], dtype=object)]})
    assert content_hash(as_lists) == content_hash(as_arrays)
    assert content_hash(as_lists) != content_hash(pd.DataFrame({"r": [["a", "c"], []]}))


def test_list_cell_with_unsupported_element_raises():
    with pytest.raises(TypeError, match="list cell"):
        content_hash(pd.DataFrame({"r": [[object()]]}))
