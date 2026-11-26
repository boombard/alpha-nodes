"""yfinance statements -> `fundamentals`: recorded canaries plus constructed variants of one payload."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from alpha_nodes.datasets import FundamentalsSchema
from alpha_nodes.providers.yfinance.fundamentals import YFStatementsPayload, normalise_fundamentals
from lensgraph.sources import NormalisedMeta

from .conftest import YF_FIXTURES

FIXTURE_SYMBOLS = sorted(
    p.stem.removeprefix("fundamentals_") for p in YF_FIXTURES.glob("fundamentals_*.json")
)
PERIODS = ["2023-12-31", "2024-12-31", "2025-12-31"]
Rows = dict[str, list[float | None]]


@pytest.fixture
def fundamentals_payload() -> Callable[[str], YFStatementsPayload]:
    """Loader for a recorded statements payload by symbol; a fresh copy per call."""

    def load(symbol: str) -> YFStatementsPayload:
        path: Path = YF_FIXTURES / f"fundamentals_{symbol}.json"
        return YFStatementsPayload.model_validate_json(path.read_text())

    return load


def _dump(rows: Rows, columns: list[str]) -> dict:
    return {"columns": columns, "index": list(rows), "data": list(rows.values())}


@pytest.fixture
def synthetic() -> Callable[..., YFStatementsPayload]:
    """Factory for a small consistent payload (three periods, assets = liabilities + equity).

    Keyword overrides replace statement rows (`income=`, `balance=`, `cashflow=`) or the
    `.info` facts (`financial_currency=`, `info_net_income=`).
    """

    def make(**overrides) -> YFStatementsPayload:
        income: Rows = {
            "Total Revenue": [100.0, 110.0, 120.0],
            "Net Income Common Stockholders": [10.0, 11.0, 12.0],
            "Diluted Average Shares": [50.0, 50.0, 50.0],
        }
        balance: Rows = {
            "Total Assets": [200.0, 210.0, 220.0],
            "Total Liabilities Net Minority Interest": [120.0, 125.0, 130.0],
            "Total Equity Gross Minority Interest": [80.0, 85.0, 90.0],
        }
        cashflow: Rows = {"Capital Expenditure": [-5.0, -6.0, -7.0]}
        return YFStatementsPayload(
            symbol="SYN",
            income=_dump(overrides.get("income", income), PERIODS),
            balance=_dump(overrides.get("balance", balance), PERIODS),
            cashflow=_dump(overrides.get("cashflow", cashflow), PERIODS),
            financial_currency=overrides.get("financial_currency", "USD"),
            info_net_income=overrides.get("info_net_income", 12.0),
        )

    return make


@pytest.mark.parametrize("symbol", FIXTURE_SYMBOLS)
def test_every_fixture_validates_against_schema(
    symbol: str, fundamentals_payload: Callable[[str], YFStatementsPayload]
) -> None:
    frame = normalise_fundamentals(fundamentals_payload(symbol))
    FundamentalsSchema.validate(frame)
    NormalisedMeta.validate(frame)
    live = frame[frame["quality_reasons"].map(lambda r: r != ["sparse_period"])]
    assert set(live["quality"]) == {"ok"}, frame["quality_reasons"].tolist()
    assert len(live) >= 3


def test_fixture_set_is_the_nine_canaries() -> None:
    assert FIXTURE_SYMBOLS == sorted(
        ["BP.L", "HSBA.L", "VOD.L", "BOOT.L", "ASML.AS", "SAP.DE", "NESN.SW", "NOVO-B.CO", "AAPL"]
    )


def test_bp_reports_usd_in_fundamentals(
    fundamentals_payload: Callable[[str], YFStatementsPayload],
) -> None:
    """BP trades in GBp but reports in USD: the statements' currency is `financialCurrency`."""
    frame = normalise_fundamentals(fundamentals_payload("BP.L"))
    assert set(frame["currency"]) == {"USD"}
    assert frame["revenue"].iloc[-1] > 1e11  # USD, not pence-scaled or divided


@pytest.mark.parametrize("symbol", FIXTURE_SYMBOLS)
def test_periods_are_annual_and_sorted(
    symbol: str, fundamentals_payload: Callable[[str], YFStatementsPayload]
) -> None:
    frame = normalise_fundamentals(fundamentals_payload(symbol))
    assert set(frame["period_type"]) == {"annual"}
    assert frame["period_end"].is_monotonic_increasing
    assert frame["period_end"].is_unique
    assert 3 <= len(frame) <= 5
    assert bool(frame["filed_at"].isna().all())
    assert bool(frame["known_at"].isna().all())


@pytest.mark.parametrize("symbol", FIXTURE_SYMBOLS)
def test_capex_positive_on_every_fixture(
    symbol: str, fundamentals_payload: Callable[[str], YFStatementsPayload]
) -> None:
    payload = fundamentals_payload(symbol)
    raw = payload.cashflow["data"][payload.cashflow["index"].index("Capital Expenditure")]
    assert any(v is not None and v < 0 for v in raw)  # Yahoo reports it negative
    frame = normalise_fundamentals(payload)
    assert bool((frame["capex"].dropna() >= 0).all())
    assert bool(frame["capex"].notna().any())
    assert all("capex_sign" in r for r in frame.loc[frame["capex"].notna(), "repairs"])


def test_bank_has_null_operating_items(
    fundamentals_payload: Callable[[str], YFStatementsPayload],
) -> None:
    frame = normalise_fundamentals(fundamentals_payload("HSBA.L"))
    frame = frame.loc[frame["quality"] != "rejected"]  # the sparse fifth column is rejected, mostly NaN
    assert len(frame) == 4
    assert bool(frame["operating_income"].isna().all())
    assert bool(frame["revenue"].notna().all())
    assert bool(frame["total_assets"].notna().all())


def test_sparse_period_rejected(synthetic: Callable[..., YFStatementsPayload]) -> None:
    """The oldest period, all NaN in the balance sheet, stays as a rejected `sparse_period` row."""
    balance = {
        "Total Assets": [None, 210.0, 220.0],
        "Total Liabilities Net Minority Interest": [None, 125.0, 130.0],
        "Total Equity Gross Minority Interest": [None, 85.0, 90.0],
    }
    frame = normalise_fundamentals(synthetic(balance=balance))
    assert [d.date().isoformat() for d in frame["period_end"]] == PERIODS
    assert frame["quality"].tolist() == ["rejected", "ok", "ok"]
    assert frame["quality_reasons"].iloc[0] == ["sparse_period"]
    assert frame["revenue"].iloc[0] == 100.0  # mapped values are kept
    assert pd.isna(frame["total_assets"].iloc[0])
    FundamentalsSchema.validate(frame)


def test_period_at_exactly_70_percent_nan_is_kept(
    synthetic: Callable[..., YFStatementsPayload],
) -> None:
    """The cut is "more than 70%": 7 of 10 rows NaN stays ok, 8 of 10 is rejected."""
    rows = lambda n_nan: {f"row{i}": [None if i < n_nan else 1.0, 1.0, 1.0] for i in range(10)}
    kept = normalise_fundamentals(synthetic(cashflow=rows(7)))
    sparse = normalise_fundamentals(synthetic(cashflow=rows(8)))
    assert kept["quality"].tolist() == ["ok", "ok", "ok"]
    assert sparse["quality"].tolist() == ["rejected", "ok", "ok"]
    assert len(sparse) == 3


def test_balance_mismatch_suspect(synthetic: Callable[..., YFStatementsPayload]) -> None:
    balance = {
        "Total Assets": [200.0, 210.0, 220.0],
        "Total Liabilities Net Minority Interest": [120.0, 125.0, 130.0],
        "Total Equity Gross Minority Interest": [80.0, 85.0, 70.0],  # last: 200 vs 220
    }
    frame = normalise_fundamentals(synthetic(balance=balance))
    assert frame["quality"].tolist() == ["ok", "ok", "suspect"]
    assert frame["quality_reasons"].iloc[-1] == ["balance_mismatch"]


def test_scale_mismatch_rejected(synthetic: Callable[..., YFStatementsPayload]) -> None:
    frame = normalise_fundamentals(synthetic(info_net_income=12.0 * 1e3))
    assert set(frame["quality"]) == {"rejected"}
    assert all("scale_mismatch" in r for r in frame["quality_reasons"])
    assert set(normalise_fundamentals(synthetic(info_net_income=12.0 / 1e6))["quality"]) == {
        "rejected"
    }


def test_close_net_income_is_not_a_scale_mismatch(
    synthetic: Callable[..., YFStatementsPayload],
) -> None:
    """Statements and `.info` legitimately differ (TTM vs fiscal year) by tens of percent."""
    assert set(normalise_fundamentals(synthetic(info_net_income=16.0))["quality"]) == {"ok"}
    assert set(normalise_fundamentals(synthetic(info_net_income=None))["quality"]) == {"ok"}


def test_no_currency_rejected(synthetic: Callable[..., YFStatementsPayload]) -> None:
    frame = normalise_fundamentals(synthetic(financial_currency=None))
    assert set(frame["quality"]) == {"rejected"}
    assert all(r == ["no_currency"] for r in frame["quality_reasons"])
    assert bool(frame["currency"].isna().all())
    FundamentalsSchema.validate(frame)  # rejected rows still satisfy the schema


def test_unknown_currency_rejected(synthetic: Callable[..., YFStatementsPayload]) -> None:
    frame = normalise_fundamentals(synthetic(financial_currency="pounds"))
    assert set(frame["quality"]) == {"rejected"}
    assert all(r == ["unknown_currency:pounds"] for r in frame["quality_reasons"])
    assert bool(frame["currency"].isna().all())
    FundamentalsSchema.validate(frame)


def test_minor_unit_currency_converted_to_major(
    synthetic: Callable[..., YFStatementsPayload],
) -> None:
    """Money is divided by 100, share counts are not; the repair is recorded."""
    frame = normalise_fundamentals(synthetic(financial_currency="GBp", info_net_income=1200.0))
    assert set(frame["currency"]) == {"GBP"}
    assert frame["revenue"].tolist() == [1.0, 1.1, 1.2]
    assert frame["capex"].tolist() == [0.05, 0.06, 0.07]
    assert frame["shares_diluted"].tolist() == [50.0, 50.0, 50.0]
    assert all("minor_unit" in r for r in frame["repairs"])
    assert set(frame["quality"]) == {"ok"}


def test_missing_item_is_nan_not_zero(synthetic: Callable[..., YFStatementsPayload]) -> None:
    frame = normalise_fundamentals(synthetic())
    assert bool(frame["operating_income"].isna().all())
    assert bool((frame["revenue"] > 0).all())


def test_empty_statements_give_empty_frame(
    synthetic: Callable[..., YFStatementsPayload],
) -> None:
    empty = {"columns": [], "index": [], "data": []}
    payload = synthetic().model_copy(update={"income": empty, "balance": empty, "cashflow": empty})
    frame = normalise_fundamentals(payload)
    assert frame.empty
    assert isinstance(frame, pd.DataFrame)


def _canary_module():
    import importlib.util

    path = Path(__file__).parents[1] / "scripts" / "canary.py"
    spec = importlib.util.spec_from_file_location("canary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canary_counts_only_non_rejected_periods(
    fundamentals_payload: Callable[[str], YFStatementsPayload],
) -> None:
    """Four good periods plus the rejected sparse one pass; three good periods pass; two fail."""
    canary = _canary_module()
    payload = fundamentals_payload("BP.L")
    frame = normalise_fundamentals(payload)
    assert len(frame) == 5
    assert canary.fundamentals_invariants(payload, frame) == []
    two = frame[frame["quality"] == "rejected"].iloc[:1]
    two = pd.concat([two, frame[frame["quality"] != "rejected"].iloc[:2]])
    assert canary.fundamentals_invariants(payload, two) == ["2 annual periods < 3"]
