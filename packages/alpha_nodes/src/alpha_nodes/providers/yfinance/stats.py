"""Raggedness statistics for recorded prices payloads.

Used by the fixture recorder to show how illiquid a name is, as evidence for the gap
threshold in the source-store hardening (see documentation/design/finance.md, Data quality).
"""

from datetime import date

from alpha_nodes import markets
from alpha_nodes.providers.yfinance.history import YFHistoryPayload
from alpha_nodes.providers.yfinance.provider import symbol_mic


def price_stats(payload: YFHistoryPayload) -> dict[str, int]:
    """Counts that show how ragged a prices payload is.

    `missing_sessions`: exchange sessions between the first and last bar with no bar;
    `zero_volume`: bars with Volume 0; `duplicate_dates`: bars sharing a local date;
    `non_session`: bars on a day the exchange calendar says was closed.
    """
    mic = symbol_mic(payload.symbol)
    days = [date.fromisoformat(ts[:10]) for ts in payload.index]
    vol = payload.columns.index("Volume")
    return {
        "bars": len(days),
        "missing_sessions": len(set(markets.sessions(mic, days[0], days[-1])) - set(days))
        if days
        else 0,
        "zero_volume": sum(1 for row in payload.data if row[vol] == 0),
        "duplicate_dates": len(days) - len(set(days)),
        "non_session": sum(1 for d in days if not markets.is_session(mic, d)),
    }
