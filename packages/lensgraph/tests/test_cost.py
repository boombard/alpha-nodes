"""LLM call ledger: pricing and per-run recording (cache hits make no call)."""

from lensgraph.cost import llm_calls_from_result, price_usd
from lensgraph.plan import NodeKey
from lensgraph.store.duckdb_index import DuckDBRunIndex


def test_price_known_model():
    price = price_usd("anthropic:claude-haiku-4-5", 1000, 500)
    assert price is not None and price > 0


def test_price_unknown_model_is_none():
    assert price_usd("anthropic:no-such-model", 10, 10) is None
    assert price_usd("nosuchprovider:x", 10, 10) is None
    assert price_usd("test", 10, 10) is None


def test_llm_calls_skip_cache_hits(toy_panel_runner):
    first = toy_panel_runner()
    calls = llm_calls_from_result(first.run_id, first)
    safety_keys = {
        k for k, v in first.values.items()
        if k.name == "safety_lens" and getattr(v, "provenance", None) and v.provenance.model
    }
    assert safety_keys and len(calls) == len(safety_keys)
    assert {c.node for c in calls} == {"safety_lens"}
    second = toy_panel_runner()
    assert llm_calls_from_result(second.run_id, second) == []


def test_llm_calls_recorded_in_index(toy_panel_runner, tmp_path):
    result = toy_panel_runner()
    expected = llm_calls_from_result(result.run_id, result)
    assert expected
    index = DuckDBRunIndex(tmp_path / "index.duckdb")
    assert index.llm_calls(result.run_id) == expected
    assert NodeKey(name="safety_lens", candidate="S1") in result.values
