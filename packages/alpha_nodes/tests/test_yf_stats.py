"""`price_stats` on a constructed payload with one of each irregularity (fixtures show none)."""

from alpha_nodes.providers.yfinance.history import YFHistoryPayload
from alpha_nodes.providers.yfinance.stats import price_stats


def _payload() -> YFHistoryPayload:
    """XLON bars: Mon 01-05, Wed 01-07 (zero volume), Wed again (duplicate), Sat 01-10."""
    bars = [
        ("2026-01-05T08:00:00+00:00", 100.0, 10.0),
        ("2026-01-07T08:00:00+00:00", 101.0, 0.0),
        ("2026-01-07T09:00:00+00:00", 101.0, 5.0),
        ("2026-01-10T08:00:00+00:00", 102.0, 5.0),
    ]
    return YFHistoryPayload(
        symbol="TEST.L",
        metadata={},
        columns=["Close", "Volume"],
        index=[b[0] for b in bars],
        data=[[b[1], b[2]] for b in bars],
        requested_start="2026-01-05",  # type: ignore[arg-type]
        requested_end="2026-01-10",  # type: ignore[arg-type]
    )


def test_price_stats_counts_each_irregularity() -> None:
    assert price_stats(_payload()) == {
        "bars": 4,
        "missing_sessions": 3,  # Tue 06, Thu 08 and Fri 09 have no bar
        "zero_volume": 1,
        "duplicate_dates": 1,
        "non_session": 1,
    }


def test_price_stats_empty_payload_is_zero() -> None:
    empty = _payload().model_copy(update={"index": [], "data": []})
    assert price_stats(empty)["bars"] == 0
