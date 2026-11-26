"""News transform: the recent, citable slice of an entity's news.

See documentation/design/finance.md, Fundamentals: datasets, providers and pinned conventions
(news), and the `quality_value` lens that consumes it.
"""

from datetime import UTC, datetime, time, timedelta
from typing import Any, ClassVar, cast

import pandas as pd
from lensgraph.node import NodeContext, TransformNode

from alpha_nodes.metrics import NewsItem
from alpha_nodes.reference import reference_day


def _opt(value: Any) -> str | None:
    """A nullable text cell as `str | None` (pandas gives NaN/None/NA for missing)."""
    return None if value is None or bool(pd.isna(value)) else str(value)


class RecentNews(TransformNode):
    """Turns the `news` frame into the newest items within a window before the reference day.

    Items published after the reference day are excluded (not yet known). The result is a
    list of `NewsItem`, newest first, so each item is citable as `recent_news[<id>]`
    (see lensgraph citations). An empty frame gives `[]`.
    """

    name: ClassVar[str] = "recent_news"
    inputs: ClassVar[dict[str, str]] = {"news": "news"}
    output: ClassVar = list

    days: int = 90  # window length, in days before the reference day
    max_items: int = 10  # cap on items returned

    def run(self, ctx: NodeContext, news: pd.DataFrame) -> list[NewsItem]:
        """The newest `max_items` items published in the `days` up to the end of the reference day."""
        if news.empty:
            return []
        day = reference_day(ctx)
        start = datetime.combine(day - timedelta(days=self.days), time.min, tzinfo=UTC)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=UTC)
        published = pd.to_datetime(news["published_at"], utc=True)
        recent = news[(published >= start) & (published < end)]
        recent = recent.assign(_ts=published[recent.index]).sort_values("_ts", ascending=False)
        return [
            NewsItem(
                id=str(row["id"]),
                published_at=cast(Any, row["_ts"]).to_pydatetime(),
                headline=str(row["headline"]),
                source=_opt(row["source"]),
                url=_opt(row["url"]),
                summary=_opt(row["summary"]),
            )
            for _, row in recent.head(self.max_items).iterrows()
        ]
