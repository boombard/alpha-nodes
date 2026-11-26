"""yfinance news payloads: the stored raw model, and its normalisation to `news`.

Items are untrusted text (finance.md, Fundamentals: datasets, providers and pinned
conventions); this module only maps fields, it never interprets them.
"""

from typing import Any

import pandas as pd
from pydantic import BaseModel

NEWS_NORMALISER_VERSION = "1"
"""Bump when `normalise_news` changes behaviour; the store then renormalises."""


class YFNewsPayload(BaseModel):
    """`Ticker.get_news(count=20)` verbatim for one symbol, JSON-safe; the stored raw payload."""

    symbol: str
    items: list[dict[str, Any]]


def _text(value: object) -> str | None:
    """A non-blank string, else None."""
    return value if isinstance(value, str) and value.strip() else None


def _nested_url(content: dict[str, Any], key: str) -> str | None:
    """`content[key]["url"]` when present."""
    inner = content.get(key)
    return _text(inner.get("url")) if isinstance(inner, dict) else None


def normalise_news(payload: YFNewsPayload) -> pd.DataFrame:
    """Map news items to `NewsSchema` rows plus the `NormalisedMeta` columns.

    `known_at` is `published_at`. Items without an id, a parseable publication time or a
    headline are skipped (there is nothing honest to put in those columns); a repeated id
    keeps its first occurrence. `source` is the provider display name, `url` the click-through
    (else canonical) URL and `summary` the item's summary (else description).
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload.items:
        raw_content = item.get("content")
        content: dict[str, Any] = raw_content if isinstance(raw_content, dict) else {}
        item_id = _text(item.get("id")) or _text(content.get("id"))
        published = pd.to_datetime(str(content.get("pubDate")), utc=True, errors="coerce")
        headline = _text(content.get("title"))
        if item_id is None or item_id in seen or pd.isna(published) or headline is None:
            continue
        seen.add(item_id)
        provider = content.get("provider")
        rows.append(
            {
                "id": item_id,
                "published_at": published,
                "headline": headline,
                "source": _text(provider.get("displayName"))
                if isinstance(provider, dict)
                else None,
                "url": _nested_url(content, "clickThroughUrl")
                or _nested_url(content, "canonicalUrl"),
                "summary": _text(content.get("summary")) or _text(content.get("description")),
            }
        )
    frame = pd.DataFrame(
        rows, columns=["id", "published_at", "headline", "source", "url", "summary"]
    )
    n = len(frame)
    text_columns = ["id", "headline", "source", "url", "summary"]
    frame = frame.astype(
        dict.fromkeys(text_columns, "str")
    )  # an empty frame is still str, not object
    frame["published_at"] = pd.to_datetime(frame["published_at"], utc=True).astype(
        "datetime64[ns, UTC]"
    )
    frame["repairs"] = pd.Series([[] for _ in range(n)], dtype="object")
    frame["quality"] = pd.Series(["ok"] * n, dtype="str")
    frame["quality_reasons"] = pd.Series([[] for _ in range(n)], dtype="object")
    frame["known_at"] = frame["published_at"]
    return frame
