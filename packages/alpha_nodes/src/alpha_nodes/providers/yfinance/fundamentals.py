"""yfinance statements payloads: the stored raw model, and its normalisation to `fundamentals`.

See documentation/design/finance.md, "Fundamentals: datasets, providers and pinned
conventions" and the yfinance quirk table (statement columns, capex sign, scale, `.info`).
"""

import json
import math
from typing import Any

import pandas as pd
from pydantic import BaseModel

from alpha_nodes.units import to_major

FUNDAMENTALS_NORMALISER_VERSION = "1"
"""Bump when `normalise_fundamentals` changes behaviour; the store then renormalises."""

SPARSE_PERIOD_NAN_SHARE = 0.7
"""A period column with a larger share of NaN rows than this is rejected (yfinance #2584)."""
BALANCE_TOLERANCE = 0.02
"""Relative gap between assets and liabilities + equity above which a period is suspect."""
SCALE_FACTORS = (1e3, 1e6)
"""Statement / `.info` net income ratios (or inverses) that point to a thousands/millions mix-up."""
SCALE_TOLERANCE = 0.2
"""Relative distance from a scale factor (in log10 space, fraction of a decade) that counts."""

_ITEMS: dict[str, tuple[str, tuple[str, ...]]] = {
    "revenue": ("income", ("Total Revenue",)),
    "operating_income": ("income", ("Operating Income",)),
    "net_income": ("income", ("Net Income Common Stockholders",)),
    "interest_expense": ("income", ("Interest Expense",)),
    "depreciation_amortization": ("cashflow", ("Depreciation And Amortization",)),
    "operating_cash_flow": ("cashflow", ("Operating Cash Flow",)),
    "capex": ("cashflow", ("Capital Expenditure",)),
    "total_assets": ("balance", ("Total Assets",)),
    "total_liabilities": ("balance", ("Total Liabilities Net Minority Interest",)),
    "total_equity": ("balance", ("Total Equity Gross Minority Interest",)),
    "common_equity": ("balance", ("Stockholders Equity",)),
    "total_debt": ("balance", ("Total Debt",)),
    "cash": ("balance", ("Cash And Cash Equivalents",)),
    "shares_diluted": ("income", ("Diluted Average Shares",)),
    "shares_outstanding": ("balance", ("Ordinary Shares Number",)),
}
"""Canonical line item -> (statement, Yahoo row labels in order of preference)."""
_COUNT_ITEMS = ("shares_diluted", "shares_outstanding")
"""Items that are share counts: never divided by a minor-unit divisor."""


class YFStatementsPayload(BaseModel):
    """Verbatim yearly statements and two `.info` facts for one symbol, JSON-safe.

    Stored as the raw payload; facts are rebuilt from it on renormalise (core.md, Source
    store). Each statement is a frame dump `{"columns": [period end ISO dates], "index":
    [Yahoo line item labels], "data": [[value or None per period] per line item]}`.
    """

    symbol: str
    income: dict[str, Any]
    balance: dict[str, Any]
    cashflow: dict[str, Any]
    financial_currency: str | None  # `.info` financialCurrency (may be a minor unit)
    info_net_income: float | None  # `.info` netIncomeToCommon, used only for the scale check


def _frame_dump(frame: pd.DataFrame) -> dict[str, Any]:
    """JSON-safe `{columns, index, data}` of a statement frame (NaN becomes None)."""
    return {
        "columns": [pd.Timestamp(c).isoformat() for c in frame.columns],
        "index": [str(i) for i in frame.index],
        "data": [
            [None if pd.isna(v) else float(v) for v in row]
            for row in frame.astype(float).itertuples(index=False, name=None)
        ],
    }


def _number(value: object) -> float | None:
    """A finite float, else None."""
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def payload_from_ticker_statements(
    symbol: str,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cashflow: pd.DataFrame,
    info: dict[str, Any],
) -> YFStatementsPayload:
    """Capture the yearly statement frames and `.info` as a `YFStatementsPayload`.

    Only `financialCurrency` and `netIncomeToCommon` are read from `.info` (finance.md,
    data quality principle 1: never its ratios).
    """
    currency = info.get("financialCurrency")
    return YFStatementsPayload(
        symbol=symbol,
        income=_frame_dump(income),
        balance=_frame_dump(balance),
        cashflow=_frame_dump(cashflow),
        financial_currency=currency if isinstance(currency, str) and currency.strip() else None,
        info_net_income=_number(json.loads(json.dumps(info.get("netIncomeToCommon"), default=str))),
    )


def _load(dump: dict[str, Any]) -> pd.DataFrame:
    """Rebuild a statement frame (rows = line items, columns = period ends) from its dump."""
    columns = pd.DatetimeIndex(pd.to_datetime(dump["columns"])).tz_localize(None).normalize()
    return pd.DataFrame(dump["data"], index=dump["index"], columns=columns, dtype=float)


def _sparse_periods(frame: pd.DataFrame) -> set[pd.Timestamp]:
    """Period columns with more than `SPARSE_PERIOD_NAN_SHARE` NaN rows."""
    if frame.empty:
        return set()
    share = frame.isna().mean(axis=0)
    return {c for c in frame.columns if bool(share[c] > SPARSE_PERIOD_NAN_SHARE)}


def _pick(frame: pd.DataFrame, labels: tuple[str, ...], period: pd.Timestamp) -> float:
    """First non-NaN value among `labels` for `period`; NaN when the row or period is absent."""
    if period not in frame.columns:
        return math.nan
    for label in labels:
        if label in frame.index and not pd.isna(value := frame.at[label, period]):
            return float(value)
    return math.nan


def _near_scale(ratio: float) -> bool:
    """True if `ratio` (or its inverse) is within tolerance of 1e3 or 1e6."""
    if ratio <= 0 or not math.isfinite(ratio):
        return False
    return any(
        abs(abs(math.log10(ratio)) - math.log10(f)) < SCALE_TOLERANCE / 2 for f in SCALE_FACTORS
    )


def normalise_fundamentals(payload: YFStatementsPayload) -> pd.DataFrame:
    """Map statements to `FundamentalsSchema` rows plus the `NormalisedMeta` columns.

    The three statements are merged on `period_end`; a period column more than 70% NaN in
    any statement (misaligned columns, yfinance #2584) is emitted with its mapped values,
    mostly NaN, as a `rejected` row with reason `sparse_period`, so it stays on record but
    default store reads skip it. All
    periods are `annual` with a null `filed_at` and `known_at` (the store stamps first sight;
    Yahoo has no filing dates). Capex is stored positive (Yahoo reports it negative; the
    `capex_sign` repair is recorded when flipped). A minor-unit reporting currency is
    converted to its major unit (money items divided, share counts untouched; `minor_unit`).
    Checks: a period whose assets differ from liabilities + equity by over 2% is `suspect`
    (`balance_mismatch`); a latest-period net income that differs from `.info` by about 1e3
    or 1e6 (taken from the latest non-sparse period) rejects every row (`scale_mismatch`);
    a missing reporting currency rejects every row (`no_currency`), as does a code `to_major`
    does not recognise (`unknown_currency:<code>`). `currency` is null on those rows; no
    guess is made.
    """
    statements = {
        "income": _load(payload.income),
        "balance": _load(payload.balance),
        "cashflow": _load(payload.cashflow),
    }
    sparse = set().union(*(_sparse_periods(f) for f in statements.values()))
    periods = sorted(set().union(*(set(f.columns) for f in statements.values())))
    divisor, currency = 1, None
    rejected: list[str] = []
    if payload.financial_currency is None:
        rejected.append("no_currency")
    else:
        try:
            currency, divisor = to_major(payload.financial_currency)
        except ValueError:
            rejected.append(f"unknown_currency:{payload.financial_currency}")
    rows: list[dict[str, Any]] = []
    for period in periods:
        row: dict[str, Any] = {"period_end": period}
        for item, (statement, labels) in _ITEMS.items():
            value = _pick(statements[statement], labels, period)
            if item == "capex":
                value = abs(value)
            if item not in _COUNT_ITEMS:
                value /= divisor
            row[item] = value
        rows.append(row)
    frame = pd.DataFrame(rows, columns=["period_end", *_ITEMS])
    n = len(frame)
    reasons: list[list[str]] = [[] for _ in range(n)]
    repairs: list[list[str]] = [[] for _ in range(n)]
    for pos, row in enumerate(frame.to_dict("records")):
        if divisor != 1:
            repairs[pos].append("minor_unit")
        raw_capex = _pick(statements["cashflow"], _ITEMS["capex"][1], row["period_end"])
        if raw_capex < 0:
            repairs[pos].append("capex_sign")
        assets, liabs, equity = row["total_assets"], row["total_liabilities"], row["total_equity"]
        if (
            not any(pd.isna(v) for v in (assets, liabs, equity))
            and assets
            and abs(assets - (liabs + equity)) / abs(assets) > BALANCE_TOLERANCE
        ):
            reasons[pos].append("balance_mismatch")
        if row["period_end"] in sparse:
            reasons[pos].append("sparse_period")
    dense = [p for p in periods if p not in sparse]
    latest = _pick(statements["income"], _ITEMS["net_income"][1], dense[-1]) if dense else math.nan
    info_ni = payload.info_net_income  # same unit as the raw statements, so compare unconverted
    if info_ni and not pd.isna(latest) and latest != 0 and _near_scale(abs(latest / info_ni)):
        rejected.append("scale_mismatch")
    out = frame.copy()
    out.insert(0, "period_type", "annual")
    out["period_end"] = pd.to_datetime(out["period_end"]).astype("datetime64[ns]")
    out.insert(2, "filed_at", pd.to_datetime([None] * n).astype("datetime64[ns]"))
    out.insert(3, "currency", pd.Series([currency] * n, dtype="str"))
    quality = [
        "rejected" if rejected or "sparse_period" in r else ("suspect" if r else "ok")
        for r in reasons
    ]
    out["repairs"] = repairs
    out["quality"] = quality
    out["quality_reasons"] = [rejected + r for r in reasons]
    out["known_at"] = pd.to_datetime([None] * n, utc=True).astype("datetime64[ns, UTC]")
    for col in (*_ITEMS,):
        out[col] = out[col].astype("float64")
    return out.reset_index(drop=True)
