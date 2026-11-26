"""yfinance news -> `news`: recorded `get_news` payloads and constructed edge cases."""

from copy import deepcopy

import pandas as pd
import pytest
from alpha_nodes.datasets import NewsSchema
from alpha_nodes.providers.yfinance.news import YFNewsPayload, normalise_news
from lensgraph.sources import NormalisedMeta

from .conftest import YF_FIXTURES

NEWS_SYMBOLS = sorted(p.stem.removeprefix("news_") for p in YF_FIXTURES.glob("news_*.json"))


def _load(symbol: str) -> YFNewsPayload:
    return YFNewsPayload.model_validate_json((YF_FIXTURES / f"news_{symbol}.json").read_text())


@pytest.mark.parametrize("symbol", NEWS_SYMBOLS)
def test_news_fixture_normalises(symbol: str) -> None:
    frame = normalise_news(_load(symbol))
    NewsSchema.validate(frame)
    NormalisedMeta.validate(frame)
    assert len(frame) > 0
    assert frame["id"].is_unique
    assert str(frame["published_at"].dtype) == "datetime64[ns, UTC]"
    assert bool((frame["known_at"] == frame["published_at"]).all())
    assert bool((frame["headline"].str.strip() != "").all())
    assert set(frame["quality"]) == {"ok"}


def test_items_without_id_skipped() -> None:
    payload = _load("AAPL")
    n = len(normalise_news(payload))
    broken = deepcopy(payload)
    first = broken.items[0]
    del first["id"]
    del first["content"]["id"]
    second = broken.items[1]
    del second["content"]["pubDate"]
    assert len(normalise_news(broken)) == n - 2


def test_repeated_id_keeps_first() -> None:
    payload = _load("AAPL")
    payload.items.append(deepcopy(payload.items[0]))
    assert len(normalise_news(payload)) == len(normalise_news(_load("AAPL")))


def test_empty_news_is_ok_empty_frame() -> None:
    frame = normalise_news(YFNewsPayload(symbol="QUIET.L", items=[]))
    assert frame.empty
    NewsSchema.validate(frame)
    NormalisedMeta.validate(frame)
    assert isinstance(frame, pd.DataFrame)
