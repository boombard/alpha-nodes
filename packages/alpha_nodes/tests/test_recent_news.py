"""RecentNews transform: window, ordering, cap and citability."""

from datetime import UTC, date, datetime

import pandas as pd
from alpha_nodes.metrics import NewsItem
from alpha_nodes.nodes.news import RecentNews
from lensgraph.citations import citable_ids
from lensgraph.node import NodeContext

TODAY = date(2026, 6, 30)
CTX = NodeContext(run_id="r", candidate=None, as_of=TODAY)


def news_frame(rows: list[tuple[str, str]]) -> pd.DataFrame:
    """Rows of (id, ISO timestamp) as a `NewsSchema`-shaped frame."""
    return pd.DataFrame(
        {
            "id": [r[0] for r in rows],
            "published_at": pd.to_datetime([r[1] for r in rows], utc=True).astype("datetime64[ns, UTC]"),
            "headline": [f"headline {r[0]}" for r in rows],
            "source": ["wire"] * len(rows),
            "url": [None] * len(rows),
            "summary": [None] * len(rows),
        }
    )


def test_recent_news_window_and_order():
    frame = news_frame(
        [
            ("old", "2026-03-01T09:00:00Z"),  # 121 days before: outside
            ("a", "2026-04-15T09:00:00Z"),
            ("future", "2026-07-02T09:00:00Z"),  # after the reference day: not yet known
            ("b", "2026-06-20T09:00:00Z"),
        ]
    )
    items = RecentNews().run(CTX, news=frame)
    assert [i.id for i in items] == ["b", "a"]
    assert all(isinstance(i, NewsItem) for i in items)
    assert items[0].published_at == datetime(2026, 6, 20, 9, tzinfo=UTC)
    assert items[0].url is None


def test_recent_news_caps_items():
    frame = news_frame([(f"n{i}", f"2026-06-{i + 1:02d}T09:00:00Z") for i in range(15)])
    items = RecentNews(max_items=4).run(CTX, news=frame)
    assert [i.id for i in items] == ["n14", "n13", "n12", "n11"]
    assert len(RecentNews().run(CTX, news=frame)) == 10


def test_empty_news_gives_empty_list():
    assert RecentNews().run(CTX, news=news_frame([])) == []


def test_items_citable_by_id():
    items = RecentNews().run(CTX, news=news_frame([("x1", "2026-06-20T09:00:00Z")]))
    assert "recent_news[x1]" in citable_ids({"recent_news": items})
