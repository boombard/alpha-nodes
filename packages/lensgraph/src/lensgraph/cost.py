"""LLM call ledger: pricing and extraction of per-run `LLMCall` records.

See documentation/design/core.md, Artifact store and run index (`llm_calls`).
"""

from genai_prices import Usage, calc_price

from .plan import RunResult
from .records import LLMCall


def price_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD cost of a call on `model` ("provider:name") from the bundled genai-prices snapshot.

    Returns None, never 0, when the model or provider is unknown or has no price. Never
    refreshes prices (no network).
    """
    provider, sep, name = model.partition(":")
    if not sep:
        return None
    try:
        price = calc_price(
            Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            model_ref=name,
            provider_id=provider,
        )
    except LookupError:
        return None
    return float(price.total_price)


def llm_calls_from_result(run_id: str, result: RunResult) -> list[LLMCall]:
    """One `LLMCall` per value whose provenance names a model, skipping cache hits.

    Cache hits made no call this run. Tokens and attempts come from the value's provenance.
    Covers AI lens verdicts and (M3.3) dossier reviews.
    """
    calls: list[LLMCall] = []
    for key, value in result.values.items():
        provenance = getattr(value, "provenance", None)
        if provenance is None or provenance.model is None:
            continue
        node_result = result.results.get(key)
        if node_result is not None and node_result.cache_hit:
            continue
        calls.append(
            LLMCall(
                run_id=run_id,
                candidate=key.candidate,
                node=key.name,
                model=provenance.model,
                attempts=provenance.attempts,
                input_tokens=provenance.input_tokens,
                output_tokens=provenance.output_tokens,
                cost_usd=price_usd(provenance.model, provenance.input_tokens,
                                   provenance.output_tokens),
            )
        )
    return calls
