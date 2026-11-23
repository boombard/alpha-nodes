import pandas as pd
from lensgraph.hashing import content_hash
from lensgraph.plan import NodeKey, NodeResult
from lensgraph.store.memory import InMemoryBlobStore, InMemoryRunIndex


def test_blob_roundtrip_and_has():
    store = InMemoryBlobStore()
    df = pd.DataFrame({"a": [1, 2]})
    h = store.put(df)
    assert h == content_hash(df)
    assert store.has(h) and not store.has("nope")
    assert store.put(df) == h
    pd.testing.assert_frame_equal(store.get(h), df)


def test_memo_lookup_and_overwrite():
    index = InMemoryRunIndex()
    assert index.lookup_memo("k") is None
    index.save_memo("k", "h1")
    assert index.lookup_memo("k") == "h1"
    index.save_memo("k", "h2")
    assert index.lookup_memo("k") == "h2"


def test_node_results_listed_per_run():
    index = InMemoryRunIndex()
    index.start_run("r1", {})
    index.start_run("r2", {})
    index.record_node("r1", NodeResult(key=NodeKey(name="a", candidate=None), status="ok"))
    index.record_node("r2", NodeResult(key=NodeKey(name="b", candidate=None), status="ok"))
    index.finish_run("r1", "ok")
    assert [r.key.name for r in index.node_results("r1")] == ["a"]
    assert index.node_results("missing") == []


def test_finish_unknown_run_does_not_raise():
    index = InMemoryRunIndex()
    index.finish_run("ghost", "ok")
    assert index.runs["ghost"]["status"] == "ok"
