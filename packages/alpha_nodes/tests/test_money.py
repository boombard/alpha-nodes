from datetime import UTC, date, datetime

import pandas as pd
import pytest
from alpha_nodes.money import CurrencyMismatch, fx_factor, require_same_currency, usd_per_unit
from alpha_nodes.reference import reference_day
from alpha_nodes.settings import FinanceSettings
from lensgraph import CandidateRef
from lensgraph.node import NodeContext
from lensgraph.sources import FakeClock


class _Store:
    """Stand-in for the `sources` service: only its clock matters to `reference_day`."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock


@pytest.fixture
def fx() -> pd.DataFrame:
    """GBP and EUR rates in the shape `FxRates` returns (an `entity` column per currency)."""
    return pd.DataFrame(
        {
            "entity": ["GBP", "GBP", "GBP", "EUR", "EUR"],
            "date": pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-12", "2026-01-02", "2026-01-05"]),
            "usd_per_unit": [1.25, 1.30, 1.40, 1.10, 1.00],
        }
    )


def test_require_same_currency_returns_the_shared_code() -> None:
    assert require_same_currency("GBP", "GBP") == "GBP"


def test_require_same_currency_raises_naming_codes() -> None:
    with pytest.raises(CurrencyMismatch) as exc:
        require_same_currency("GBP", "USD", "GBP", "EUR")
    assert all(code in str(exc.value) for code in ("GBP", "USD", "EUR"))
    assert isinstance(exc.value, ValueError)


def test_usd_per_unit_usd_is_one() -> None:
    assert usd_per_unit(pd.DataFrame(), "USD", date(2026, 1, 5)) == 1.0


def test_usd_per_unit_takes_last_rate_on_or_before(fx: pd.DataFrame) -> None:
    assert usd_per_unit(fx, "GBP", date(2026, 1, 5)) == 1.30
    assert usd_per_unit(fx, "GBP", date(2026, 1, 9)) == 1.30  # weekend/holiday gap: last prior rate
    assert usd_per_unit(fx, "GBP", date(2026, 1, 12)) == 1.40


def test_usd_per_unit_none_when_stale_or_missing(fx: pd.DataFrame) -> None:
    assert usd_per_unit(fx, "GBP", date(2026, 1, 1)) is None  # nothing on or before
    assert usd_per_unit(fx, "EUR", date(2026, 1, 13)) is None  # last EUR rate is 8 days old
    assert usd_per_unit(fx, "EUR", date(2026, 1, 12), max_stale_days=7) == 1.00
    assert usd_per_unit(fx, "CHF", date(2026, 1, 5)) is None  # no such currency
    assert usd_per_unit(fx.iloc[0:0], "GBP", date(2026, 1, 5)) is None


def test_usd_per_unit_with_duplicated_index() -> None:
    gbp = pd.DataFrame({"entity": "GBP", "date": pd.to_datetime(["2026-01-02", "2026-01-05"]), "usd_per_unit": [1.25, 1.30]})
    eur = pd.DataFrame({"entity": "EUR", "date": pd.to_datetime(["2026-01-02", "2026-01-05"]), "usd_per_unit": [1.10, 1.00]})
    fx = pd.concat([gbp, eur])  # index 0, 1, 0, 1
    assert usd_per_unit(fx, "GBP", date(2026, 1, 5)) == 1.30
    assert usd_per_unit(fx, "EUR", date(2026, 1, 5)) == 1.00


def test_fx_factor_cross_rate(fx: pd.DataFrame) -> None:
    assert fx_factor(fx, "GBP", "EUR", date(2026, 1, 5)) == pytest.approx(1.30 / 1.00)
    assert fx_factor(fx, "GBP", "USD", date(2026, 1, 5)) == pytest.approx(1.30)
    assert fx_factor(fx, "USD", "GBP", date(2026, 1, 5)) == pytest.approx(1 / 1.30)
    assert fx_factor(fx, "GBP", "CHF", date(2026, 1, 5)) is None  # a missing rate is never 1.0


def test_fx_factor_same_currency_needs_no_fx() -> None:
    assert fx_factor(pd.DataFrame(), "GBP", "GBP", date(2026, 1, 5)) == 1.0


def _ctx(as_of: date | None, services: dict) -> NodeContext:
    return NodeContext(run_id="r", candidate=CandidateRef(id="X"), as_of=as_of, services=services)


def test_reference_day_prefers_as_of_then_store_clock() -> None:
    store = _Store(FakeClock(datetime(2026, 3, 10, 23, 30, tzinfo=UTC)))
    assert reference_day(_ctx(date(2025, 6, 30), {"sources": store})) == date(2025, 6, 30)
    assert reference_day(_ctx(None, {"sources": store})) == date(2026, 3, 10)
    assert reference_day(_ctx(None, {})) == datetime.now(UTC).date()


def test_finance_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPHA_NODES_SEC_USER_AGENT", raising=False)
    assert FinanceSettings(_env_file=None).sec_user_agent is None  # pyright: ignore[reportCallIssue]
    monkeypatch.setenv("ALPHA_NODES_SEC_USER_AGENT", "Someone someone@example.test")
    assert FinanceSettings().sec_user_agent == "Someone someone@example.test"
