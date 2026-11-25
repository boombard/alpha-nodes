"""Exchange calendars keyed by MIC, and the settled cut-off for date-axis datasets.

A trading day is "settled" once its close plus `SETTLE_DELAY` has passed; the source
store treats later days as the unsettled tail. See documentation/design/finance.md,
Prices and point-in-time, and core.md, Source store.
"""

from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import cast

import exchange_calendars as xcals
import pandas as pd

SETTLE_DELAY = timedelta(minutes=30)
"""Grace after the close before that session's data is considered final."""

_CALENDARS: dict[str, str] = {
    "XLON": "XLON",
    "XPAR": "XPAR",
    "XAMS": "XAMS",
    "XBRU": "XBRU",
    "XLIS": "XLIS",
    "XDUB": "XDUB",
    "XETR": "XETR",
    "XMIL": "XMIL",
    "XMAD": "XMAD",
    "XSWX": "XSWX",
    "XSTO": "XSTO",
    "XCSE": "XCSE",
    "XOSL": "XOSL",
    "XHEL": "XHEL",
    "XNYS": "XNYS",
    "XNAS": "XNYS",  # NASDAQ trades on the NYSE calendar
}
MICS: frozenset[str] = frozenset(_CALENDARS)
"""Market identifier codes this domain supports."""


@cache
def _calendar(mic: str) -> xcals.ExchangeCalendar:
    try:
        name = _CALENDARS[mic]
    except KeyError:
        raise ValueError(f"unknown MIC: {mic!r}") from None
    return xcals.get_calendar(name)


def _ts(day: date) -> pd.Timestamp:
    return cast(pd.Timestamp, pd.Timestamp(day.isoformat()))


def is_session(mic: str, day: date) -> bool:
    """True if the exchange trades on `day` (local trading date)."""
    cal = _calendar(mic)
    return bool(cal.is_session(_ts(day))) if _in_range(cal, day) else False


def _in_range(cal: xcals.ExchangeCalendar, day: date) -> bool:
    return cal.first_session <= _ts(day) <= cal.last_session


def sessions(mic: str, start: date, end: date) -> list[date]:
    """Trading dates in [start, end], inclusive."""
    cal = _calendar(mic)
    return [s.date() for s in cal.sessions_in_range(_ts(start), _ts(end))]


def session_close(mic: str, day: date) -> datetime:
    """Closing time of the session on `day` as tz-aware UTC; ValueError if not a session."""
    cal = _calendar(mic)
    if not is_session(mic, day):
        raise ValueError(f"{day} is not a {mic} session")
    return cal.session_close(_ts(day)).to_pydatetime().astimezone(UTC)


def settled_through(mic: str, now: datetime) -> date | None:
    """Last session whose close + `SETTLE_DELAY` is <= `now`; None if there is none."""
    cal = _calendar(mic)
    cutoff = pd.Timestamp(now.astimezone(UTC) - SETTLE_DELAY)
    closes = cal.closes
    n = int(closes.searchsorted(cutoff, side="right"))  # type: ignore[arg-type]
    return cast(pd.Timestamp, closes.index[n - 1]).date() if n else None


def fx_settled_through(now: datetime) -> date:
    """FX trades round the clock, so the settled cut-off is the previous UTC day."""
    return now.astimezone(UTC).date() - timedelta(days=1)
