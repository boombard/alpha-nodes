"""yfinance payload normalisation, from recorded fixtures plus clearly constructed variants."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from alpha_nodes import markets
from alpha_nodes.datasets import FxSchema, PriceSchema
from alpha_nodes.providers.yfinance.history import (
    FX_NORMALISER_VERSION,
    PRICES_NORMALISER_VERSION,
    YFHistoryPayload,
    normalise_fx,
    normalise_prices,
)
from alpha_nodes.providers.yfinance.provider import symbol_mic as markets_mic
from lensgraph.sources import NormalisedMeta

from .conftest import YF_FIXTURES

Loader = Callable[[str], YFHistoryPayload]

PRICE_FIXTURES = {
    "BP.L": "XLON",
    "HSBA.L": "XLON",
    "VOD.L": "XLON",
    "ASML.AS": "XAMS",
    "SAP.DE": "XETR",
    "NESN.SW": "XSWX",
    "NOVO-B.CO": "XCSE",
    "AAPL": "XNYS",
}
FX_FIXTURES = ["GBPUSD=X", "EURUSD=X", "CHFUSD=X", "DKKUSD=X"]


def _col(payload: YFHistoryPayload, name: str) -> int:
    return payload.columns.index(name)


def _row_of(payload: YFHistoryPayload, day: date) -> int:
    return next(i for i, ts in enumerate(payload.index) if ts[:10] == day.isoformat())


def _prices(load: Loader, symbol: str) -> tuple[YFHistoryPayload, pd.DataFrame]:
    payload = load(f"prices_{symbol}")
    return payload, normalise_prices(payload, PRICE_FIXTURES[symbol])


def test_gbp_minor_unit_repaired(yf_payload: Loader) -> None:
    payload, frame = _prices(yf_payload, "BP.L")
    assert payload.metadata["currency"] == "GBp"
    assert set(frame["currency"]) == {"GBP"}
    assert all("minor_unit" in r for r in frame["repairs"])
    raw_close = payload.data[-1][_col(payload, "Close")]
    assert frame["close"].iloc[-1] == pytest.approx(raw_close / 100)  # type: ignore[arg-type]


@pytest.mark.parametrize(("symbol", "currency"), [("ASML.AS", "EUR"), ("NESN.SW", "CHF")])
def test_eur_and_chf_unchanged(yf_payload: Loader, symbol: str, currency: str) -> None:
    payload, frame = _prices(yf_payload, symbol)
    assert set(frame["currency"]) == {currency}
    assert not any("minor_unit" in r for r in frame["repairs"])
    assert frame["close"].iloc[-1] == pytest.approx(payload.data[-1][_col(payload, "Close")])  # type: ignore[arg-type]


@pytest.mark.parametrize("symbol", list(PRICE_FIXTURES))
def test_prices_output_validates_against_schema(yf_payload: Loader, symbol: str) -> None:
    _, frame = _prices(yf_payload, symbol)
    assert not frame.empty
    PriceSchema.validate(frame)
    NormalisedMeta.validate(frame)


@pytest.mark.parametrize("symbol", FX_FIXTURES)
def test_fx_output_validates_against_schema(yf_payload: Loader, symbol: str) -> None:
    frame = normalise_fx(yf_payload(f"fx_{symbol}"))
    assert not frame.empty
    FxSchema.validate(frame)
    NormalisedMeta.validate(frame)


def test_yahoo_repair_flag_recorded(yf_payload: Loader) -> None:
    """A true `Repaired?` flag becomes a `yf_price_repair` repair (constructed copy)."""
    payload = yf_payload("prices_NESN.SW")
    payload.data[10][_col(payload, "Repaired?")] = 1.0
    frame = normalise_prices(payload, "XSWX")
    assert frame["repairs"].iloc[10] == ["yf_price_repair"]
    assert frame["repairs"].iloc[11] == []


def test_x100_jump_marked_suspect(yf_payload: Loader) -> None:
    """Constructed variant: one ASML close multiplied by 100."""
    payload = yf_payload("prices_ASML.AS")
    payload.data[100][_col(payload, "Close")] *= 100  # type: ignore[operator]
    frame = normalise_prices(payload, "XAMS")
    assert frame["quality"].iloc[100] == "suspect"
    assert "jump_x100" in frame["quality_reasons"].iloc[100]
    assert frame["close"].iloc[100] > 10_000  # value kept, not repaired
    assert frame["quality"].iloc[50] == "ok"


def test_dividend_yield_over_25pct_marked_suspect(yf_payload: Loader) -> None:
    """Constructed variant: a dividend of 30% of the close."""
    payload = yf_payload("prices_ASML.AS")
    close = payload.data[60][_col(payload, "Close")]
    payload.data[60][_col(payload, "Dividends")] = close * 0.3  # type: ignore[operator]
    frame = normalise_prices(payload, "XAMS")
    assert frame["quality"].iloc[60] == "suspect"
    assert "dividend_yield_gt_25pct" in frame["quality_reasons"].iloc[60]


def test_non_session_bar_marked_suspect(yf_payload: Loader) -> None:
    """Constructed variant: a copy of one ASML bar re-dated to a Sunday."""
    payload = yf_payload("prices_ASML.AS")
    sunday = "2025-12-07T00:00:00+01:00"
    pos = next(i for i, ts in enumerate(payload.index) if ts > sunday)
    payload.index.insert(pos, sunday)
    payload.data.insert(pos, list(payload.data[pos]))
    frame = normalise_prices(payload, "XAMS")
    bar = frame[frame["date"] == pd.Timestamp("2025-12-07")].iloc[0]
    assert bar["quality"] == "suspect"
    assert "non_session_bar" in bar["quality_reasons"]
    assert pd.isna(bar["known_at"])


def test_missing_sessions_marked_suspect(yf_payload: Loader) -> None:
    """Constructed variant: four consecutive ASML sessions removed."""
    payload = yf_payload("prices_ASML.AS")
    del payload.index[50:54]
    del payload.data[50:54]
    frame = normalise_prices(payload, "XAMS")
    assert frame["quality"].iloc[50] == "suspect"
    assert "missing_sessions:4" in frame["quality_reasons"].iloc[50]


def test_non_positive_close_rejected(yf_payload: Loader) -> None:
    """Constructed variant: a NaN close and a zero close."""
    payload = yf_payload("prices_ASML.AS")
    payload.data[20][_col(payload, "Close")] = None
    payload.data[30][_col(payload, "Close")] = 0.0
    frame = normalise_prices(payload, "XAMS")
    assert list(frame["quality"].iloc[[20, 30]]) == ["rejected", "rejected"]
    assert frame["quality"].iloc[21] == "ok"


def test_known_at_is_session_close(yf_payload: Loader) -> None:
    _, frame = _prices(yf_payload, "BP.L")
    day = frame["date"].iloc[-1].date()
    assert frame["known_at"].iloc[-1] == pd.Timestamp(markets.session_close("XLON", day))


def test_fx_rate_is_usd_per_unit(yf_payload: Loader) -> None:
    frame = normalise_fx(yf_payload("fx_GBPUSD=X"))
    assert bool((frame["usd_per_unit"] > 1).all())
    day = frame["date"].iloc[-1].date()
    end_of_day = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)
    assert frame["known_at"].iloc[-1] == pd.Timestamp(end_of_day)


def test_split_ratio_and_dividends_mapped(yf_payload: Loader) -> None:
    frame = normalise_prices(yf_payload("split_AAPL"), "XNYS")
    assert frame["split_ratio"].tolist() == [1.0, 4.0, 1.0, 1.0, 1.0]
    assert bool((frame["dividends"] == 0.0).all())


def test_empty_payload_gives_empty_valid_frame(yf_payload: Loader) -> None:
    payload = yf_payload("prices_AAPL")
    payload.index, payload.data = [], []
    frame = normalise_prices(payload, "XNYS")
    assert frame.empty
    assert {"date", "close", "repairs", "quality", "known_at"} <= set(frame.columns)


NEW_REASON_PREFIXES = (
    "duplicate_bar",
    "split_like_jump",
    "unadjusted_split",
    "dividend_yield_lt_0.02pct",
    "stale",
    "fx_jump",
    "missing_sessions",
)


def _reasons(frame: pd.DataFrame, i: int) -> list[str]:
    return list(frame["quality_reasons"].iloc[i])


def test_normaliser_versions_bumped() -> None:
    assert PRICES_NORMALISER_VERSION == FX_NORMALISER_VERSION == "2"


def test_duplicate_bar_collapsed_and_marked(yf_payload: Loader) -> None:
    """Constructed variant: ASML bar 40 duplicated; the first copy has a NaN close and the
    dividend, the second the close; the kept row carries both."""
    payload = yf_payload("prices_ASML.AS")
    base = payload.data[40]
    first, second = list(base), list(base)
    first[_col(payload, "Close")] = None
    first[_col(payload, "Dividends")] = 0.5
    second[_col(payload, "Dividends")] = 0.0
    payload.index.insert(40, payload.index[40])
    payload.data[40:41] = [first, second]
    day = date.fromisoformat(payload.index[40][:10])
    frame = normalise_prices(payload, "XAMS")
    rows = frame[frame["date"] == pd.Timestamp(day)]
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["close"] == pytest.approx(base[_col(payload, "Close")])  # type: ignore[arg-type]
    assert row["dividends"] == pytest.approx(0.5)
    assert "duplicate_bar" in row["quality_reasons"]
    assert row["quality"] == "suspect"


def test_single_missing_session_marked(yf_payload: Loader) -> None:
    """Constructed variant: one ASML session removed."""
    payload = yf_payload("prices_ASML.AS")
    del payload.index[50], payload.data[50]
    frame = normalise_prices(payload, "XAMS")
    assert "missing_sessions:1" in _reasons(frame, 50)


@pytest.mark.parametrize(("factor", "split_row"), [(0.5, False), (2.0, False), (0.25, True)])
def test_split_like_jump_marked(yf_payload: Loader, factor: float, split_row: bool) -> None:
    """Constructed variant: the closes from bar 100 on are scaled; reason depends on a split row.

    A split-sized jump with a split row that day means the close was not split-adjusted.
    """
    payload = yf_payload("prices_ASML.AS")
    for row in payload.data[100:]:
        row[_col(payload, "Close")] *= factor  # type: ignore[operator]
    if split_row:
        payload.data[100][_col(payload, "Stock Splits")] = 4.0
    frame = normalise_prices(payload, "XAMS")
    expected = "unadjusted_split" if split_row else "split_like_jump"
    other = "split_like_jump" if split_row else "unadjusted_split"
    assert expected in _reasons(frame, 100)
    assert other not in _reasons(frame, 100)
    assert frame["quality"].iloc[100] == "suspect"
    assert not any(r.startswith(("split_like", "unadjusted")) for r in _reasons(frame, 101))


def test_unadjusted_split_marked(yf_payload: Loader) -> None:
    """Constructed variant: a 1:4 move on a day with a 4.0 split row."""
    payload = yf_payload("prices_ASML.AS")
    payload.data[70][_col(payload, "Close")] *= 0.25  # type: ignore[operator]
    payload.data[70][_col(payload, "Stock Splits")] = 4.0
    payload.data[71][_col(payload, "Close")] = payload.data[70][_col(payload, "Close")]
    frame = normalise_prices(payload, "XAMS")
    assert "unadjusted_split" in _reasons(frame, 70)


def test_tiny_dividend_marked(yf_payload: Loader) -> None:
    """Constructed variant: a dividend 0.01% of the close (a pounds-vs-pence mix-up)."""
    payload = yf_payload("prices_ASML.AS")
    close = payload.data[60][_col(payload, "Close")]
    payload.data[60][_col(payload, "Dividends")] = close * 0.0001  # type: ignore[operator]
    frame = normalise_prices(payload, "XAMS")
    assert "dividend_yield_lt_0.02pct" in _reasons(frame, 60)
    assert "dividend_yield_lt_0.02pct" not in _reasons(frame, 61)


def _flat_run(payload: YFHistoryPayload, start: int, length: int, volume: float | None) -> None:
    close = payload.data[start][_col(payload, "Close")]
    for row in payload.data[start : start + length]:
        row[_col(payload, "Close")] = close
        row[_col(payload, "Volume")] = volume


def test_stale_run_marked(yf_payload: Loader) -> None:
    """Constructed variant: 5 identical closes. With NaN volume every bar of the run is stale;
    with zero volume (genuine no-trade on illiquid names, finance.md) none is."""
    payload = yf_payload("prices_ASML.AS")
    _flat_run(payload, 80, 5, None)
    frame = normalise_prices(payload, "XAMS")
    assert all("stale" in _reasons(frame, i) for i in range(80, 85))
    assert "stale" not in _reasons(frame, 79)
    assert "stale" not in _reasons(frame, 85)

    zero = yf_payload("prices_ASML.AS")
    _flat_run(zero, 80, 5, 0.0)
    frame = normalise_prices(zero, "XAMS")
    assert not any("stale" in _reasons(frame, i) for i in range(len(frame)))

    short = yf_payload("prices_ASML.AS")
    _flat_run(short, 80, 4, None)
    frame = normalise_prices(short, "XAMS")
    assert not any("stale" in _reasons(frame, i) for i in range(80, 84))


def test_fx_jump_and_stale_marked(yf_payload: Loader) -> None:
    """Constructed variant: one GBP rate up 12%, and five identical consecutive rates."""
    payload = yf_payload("fx_GBPUSD=X")
    close = _col(payload, "Close")
    for row in payload.data[100:]:
        row[close] *= 1.12  # type: ignore[operator]
    for row in payload.data[150:155]:
        row[close] = payload.data[150][close]
    frame = normalise_fx(payload)
    assert "fx_jump" in _reasons(frame, 100)
    assert "fx_jump" not in _reasons(frame, 101)
    assert all("stale" in _reasons(frame, i) for i in range(150, 155))
    assert "stale" not in _reasons(frame, 149)
    assert "stale" not in _reasons(frame, 155)


@pytest.mark.parametrize(
    "name",
    sorted(
        p.stem
        for p in YF_FIXTURES.glob("*.json")
        if p.stem.startswith(("prices_", "fx_", "split_"))
    ),
)
def test_recorded_fixtures_have_no_new_suspects(yf_payload: Loader, name: str) -> None:
    """Guards against false positives of the new checks on clean recorded data (BMT.L included)."""
    payload = yf_payload(name)
    if name.startswith("fx_"):
        frame = normalise_fx(payload)
    else:
        symbol = payload.symbol
        mic = PRICE_FIXTURES.get(symbol) or markets_mic(symbol)
        frame = normalise_prices(payload, mic)
    for reasons in frame["quality_reasons"]:
        assert not [r for r in reasons if r.startswith(NEW_REASON_PREFIXES)], reasons
