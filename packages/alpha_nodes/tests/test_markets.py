from datetime import UTC, date, datetime

import pytest
from alpha_nodes.markets import (
    MICS,
    fx_settled_through,
    is_session,
    session_close,
    sessions,
    settled_through,
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_settled_before_and_after_close() -> None:
    # 2026-01-07 is a Wednesday; XLON closes 16:30 UTC in winter.
    assert settled_through("XLON", utc(2026, 1, 7, 15, 0)) == date(2026, 1, 6)
    close = session_close("XLON", date(2026, 1, 7))
    assert close == utc(2026, 1, 7, 16, 30)
    assert settled_through("XLON", utc(2026, 1, 7, 16, 59)) == date(2026, 1, 6)
    assert settled_through("XLON", utc(2026, 1, 7, 17, 1)) == date(2026, 1, 7)


def test_settled_over_weekend_and_holiday() -> None:
    assert settled_through("XLON", utc(2026, 1, 10, 12, 0)) == date(2026, 1, 9)  # Saturday
    # 2026-12-28 is the UK Boxing Day bank holiday (substitute); Mon 12-21..Fri 12-24 trade.
    assert not is_session("XLON", date(2026, 12, 28))
    assert settled_through("XLON", utc(2026, 12, 28, 23, 0)) == date(2026, 12, 24)


def test_settled_per_exchange_timezone() -> None:
    now = utc(2026, 1, 7, 17, 0)  # XETR closed 16:30 UTC; XNYS (14:00 local close ~21:00 UTC) open
    assert settled_through("XETR", now) == date(2026, 1, 7)
    assert settled_through("XNYS", now) == date(2026, 1, 6)


def test_xnas_shares_xnys_calendar() -> None:
    assert session_close("XNAS", date(2026, 1, 7)) == session_close("XNYS", date(2026, 1, 7))


def test_fx_settled_is_previous_utc_day() -> None:
    assert fx_settled_through(utc(2026, 1, 7, 0, 5)) == date(2026, 1, 6)
    assert fx_settled_through(utc(2026, 1, 7, 23, 59)) == date(2026, 1, 6)


def test_sessions_range_and_non_session_close() -> None:
    assert sessions("XLON", date(2026, 1, 8), date(2026, 1, 12)) == [
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
    ]
    with pytest.raises(ValueError):
        session_close("XLON", date(2026, 1, 10))


def test_unknown_mic_raises() -> None:
    with pytest.raises(ValueError, match="XXXX"):
        is_session("XXXX", date(2026, 1, 7))
    assert "XLON" in MICS and len(MICS) == 16
