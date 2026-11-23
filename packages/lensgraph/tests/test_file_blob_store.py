from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from lensgraph.hashing import content_hash
from lensgraph.store.files import FileBlobStore, FsspecBlobStore
from lensgraph.store.memory import InMemoryBlobStore
from lensgraph.types import Absent
from toy.nodes import ToxNote


@pytest.fixture(params=["file", "memory"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> FsspecBlobStore:
    """Every blob-store test runs against both the local-file and the in-memory backend."""
    if request.param == "file":
        return FileBlobStore(tmp_path / "blobs")
    return InMemoryBlobStore()


def _files(store: FsspecBlobStore) -> list[str]:
    """Paths of every blob file (or leftover temp file) under the store's root."""
    return store.fs.find(store.root) if store.fs.exists(store.root) else []


def _tz_frame() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="America/New_York")
    return pd.DataFrame({"px": [1.0, 2.0, 3.0]}, index=idx)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame({"a": pd.Series([], dtype="float64"), "b": pd.Series([], dtype="object")})


@pytest.mark.parametrize(
    "value",
    [
        1.5,
        3,
        "s",
        None,
        [1.0, 2.0],
        {"a": 1},
        ToxNote(id="n1", text="x"),
        [ToxNote(id="n1", text="x"), ToxNote(id="n2", text="y")],
        {"k": ToxNote(id="n1", text="x")},
        Absent(reason="r"),
    ],
)
def test_roundtrip_types(store: FsspecBlobStore, value: Any) -> None:
    assert store.get(store.put(value)) == value


def test_roundtrip_numpy_scalar(store: FsspecBlobStore) -> None:
    out = store.get(store.put(np.float64(2.5)))
    assert out == 2.5 and type(out) is float


@pytest.mark.parametrize("make", [_empty_frame, _tz_frame])
def test_roundtrip_frames(store: FsspecBlobStore, make: Any) -> None:
    df = make()
    # Parquet does not store DatetimeIndex.freq; values, tz and dtypes must match.
    pd.testing.assert_frame_equal(store.get(store.put(df)), df, check_freq=False)


def test_frames_are_parquet_and_models_json(store: FsspecBlobStore) -> None:
    h1 = store.put(_tz_frame())
    h2 = store.put(ToxNote(id="n1", text="x"))
    assert {Path(p).suffix for p in _files(store)} == {".parquet", ".json"}
    assert store.has(h1) and store.has(h2) and not store.has("0" * 64)


def test_put_idempotent_and_hash_is_content_hash(store: FsspecBlobStore) -> None:
    v = [ToxNote(id="n1", text="x")]
    h = store.put(v)
    assert h == content_hash(v)
    assert store.put(v) == h
    assert len(_files(store)) == 1


def test_unsupported_type_raises(store: FsspecBlobStore) -> None:
    with pytest.raises(TypeError):
        store.put(object())
    with pytest.raises(TypeError):
        store.put([object()])


def test_blob_persistence_across_instances(tmp_path: Path) -> None:
    h = FileBlobStore(tmp_path).put(ToxNote(id="n1", text="x"))
    assert FileBlobStore(tmp_path).get(h) == ToxNote(id="n1", text="x")


def test_unwritable_frame_raises_type_error_and_leaves_no_files(store: FsspecBlobStore) -> None:
    with pytest.raises(TypeError, match="cannot store frame"):
        store.put(pd.DataFrame({"a": pd.Series([1, "a"], dtype="object")}))
    assert _files(store) == []


def test_memory_store_returns_copy() -> None:
    store = InMemoryBlobStore()
    df = pd.DataFrame({"a": [1, 2]})
    h = store.put(df)
    df.loc[0, "a"] = 99
    assert store.get(h)["a"].tolist() == [1, 2]


def test_memory_stores_are_isolated() -> None:
    a, b = InMemoryBlobStore(), InMemoryBlobStore()
    h = a.put("x")
    assert a.has(h) and not b.has(h)
