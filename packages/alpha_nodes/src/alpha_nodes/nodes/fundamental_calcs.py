"""Fundamentals calc nodes behind the AI lenses (top calculation layer).

`annual_fundamentals` picks the annual periods known on the run's reference day; the four
metric nodes read that frame through the adapters in `alpha_nodes.statements` and the kernels
in `alpha_nodes.kernels`, and return result models whose fields the lenses cite. They hold no
maths of their own, and declare what they call in `code_deps`. Conventions are pinned in
documentation/design/finance.md (Fundamentals: pinned conventions).

A line item missing from the periods gives a None field, never a failure; an empty frame gives
`periods=0` results. Like the price calc nodes, none is memoized (`memoize = False`): they cost
milliseconds and their outputs are stored for lineage anyway (Calculation layers).
"""

from collections.abc import Callable
from datetime import date
from typing import ClassVar, cast

import numpy as np
import pandas as pd
from lensgraph.node import CalcNode, NodeContext, TransformNode

from alpha_nodes.conventions import MAX_ANNUAL_PERIODS
from alpha_nodes.kernels import (
    cagr,
    coefficient_of_variation,
    growth,
    mean_std,
    owner_earnings,
    safe_ratio,
    sum_ratio,
)
from alpha_nodes.metrics import (
    BalanceSheetResult,
    CashGenerationResult,
    FundamentalTrendResult,
    PeriodWindow,
    ProfitabilityResult,
)
from alpha_nodes.reference import reference_day
from alpha_nodes.statements import (
    AnnualFundamentalsSchema,
    annual_periods,
    known_on,
    latest_complete,
    period_window,
    values,
    years_between,
)

_WINDOW_DEPS = (values, period_window)
_MAX_STEP_YEARS = 1.5  # a "1y" step across more than 18 months is None; finance.md, Fundamentals pinned conventions (Growth)
_BASE_TOLERANCE_DAYS = 183  # the 3y base may sit up to 6 months off three years back; finance.md, Fundamentals pinned conventions (Growth)
_OE_COLUMNS = ("net_income", "depreciation_amortization", "capex")
_TREND_YEARS = 3  # revenue_cagr_3y base: the period about 3 years before the latest


def _opt(value: float) -> float | None:
    """A kernel's `nan` ("cannot be computed") as None."""
    return None if np.isnan(value) else float(value)


def _widest(*windows: PeriodWindow) -> PeriodWindow:
    """The window with the most periods (the first of equals): the one reported for a multi-field result."""
    return max(windows, key=lambda w: w.periods)


def _span(annual: pd.DataFrame, *windows: PeriodWindow) -> PeriodWindow:
    """The window from the earliest start among `windows` (ignoring empty ones) to the latest period of `annual`.

    Same convention as `BalanceSheet` and `FundamentalTrend`: from the oldest row any field used
    to the latest period. An empty `annual` gives the empty window.
    """
    if annual.empty:
        return period_window(annual)
    last = annual["period_end"].iloc[-1]
    starts = [pd.Timestamp(w.first_period_end) for w in windows if w.periods and w.first_period_end]
    first = min(starts, default=last)
    return period_window(
        cast(pd.DataFrame, annual[(annual["period_end"] >= first) & (annual["period_end"] <= last)])
    )


def _col(frame: pd.DataFrame, name: str) -> np.ndarray:
    """A column as a float64 array."""
    return frame[name].to_numpy(float)


def _fcf(frame: pd.DataFrame) -> np.ndarray:
    """Free cash flow per row, `operating_cash_flow - capex` (finance.md, Pinned conventions); `nan` where either is missing."""
    return _col(frame, "operating_cash_flow") - _col(frame, "capex")


def _ratio_on(row: pd.DataFrame, num: str, den: str) -> float:
    """`num / den` on a single-row frame via `safe_ratio`; `nan` when `row` is empty or `den <= 0`."""
    return float(safe_ratio(_col(row, num), _col(row, den))[0]) if len(row) else float("nan")


def _latest_point(
    annual: pd.DataFrame, fields: dict[str, tuple[str, ...]]
) -> tuple[dict[str, pd.DataFrame], dict[str, date], PeriodWindow]:
    """Per field, its `latest_complete` row; plus `field_periods` for the older ones and the window.

    `fields` maps a result field to the columns it needs. The window spans from the oldest row
    used (or the latest period if none qualified) to the latest period.
    """
    rows = {name: latest_complete(annual, *cols) for name, cols in fields.items()}
    if annual.empty:
        return rows, {}, period_window(annual)
    last_end = annual["period_end"].iloc[-1]
    used = [r["period_end"].iloc[0] for r in rows.values() if len(r)]
    oldest = min(used, default=last_end)
    stale = {n: r["period_end"].iloc[0].date() for n, r in rows.items() if len(r) and r["period_end"].iloc[0] < last_end}
    return rows, stale, period_window(cast(pd.DataFrame, annual[annual["period_end"] >= oldest]))


class AnnualFundamentals(TransformNode):
    """The annual periods of the `fundamentals` frame known on the run's reference day.

    Attributes:
        max_periods: most periods kept (the latest).
    """

    name: ClassVar[str] = "annual_fundamentals"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"fundamentals": "fundamentals"}
    output: ClassVar = AnnualFundamentalsSchema
    code_deps: ClassVar = (annual_periods, known_on, reference_day)
    max_periods: int = MAX_ANNUAL_PERIODS

    def run(self, ctx: NodeContext, fundamentals: pd.DataFrame) -> pd.DataFrame:
        """Return the `AnnualFundamentalsSchema` frame as known on `reference_day(ctx)`."""
        return annual_periods(fundamentals, reference_day(ctx), self.max_periods)


class Profitability(CalcNode):
    """ROE, operating margin and earnings stability across the window.

    The reported window is the widest of the ROE, margin and net-income period sets.
    """

    name: ClassVar[str] = "profitability"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"annual": "annual_fundamentals"}
    output: ClassVar = ProfitabilityResult
    code_deps: ClassVar = (safe_ratio, mean_std, coefficient_of_variation, _opt, *_WINDOW_DEPS)

    def run(self, ctx: NodeContext, annual: pd.DataFrame) -> ProfitabilityResult:
        """Compute the profitability fields over `annual`."""
        roe_rows, roe_win = values(annual, "net_income", "common_equity")
        mgn_rows, mgn_win = values(annual, "operating_income", "revenue")
        ni_rows, ni_win = values(annual, "net_income")
        roe = safe_ratio(_col(roe_rows, "net_income"), _col(roe_rows, "common_equity"))
        roe = roe[~np.isnan(roe)]  # non-positive equity periods have no ROE
        margin = safe_ratio(_col(mgn_rows, "operating_income"), _col(mgn_rows, "revenue"))
        margin = margin[~np.isnan(margin)]
        roe_mean, roe_std = mean_std(roe)
        mgn_mean, mgn_std = mean_std(margin)
        net_income = _col(ni_rows, "net_income")
        return ProfitabilityResult(
            **_widest(roe_win, mgn_win, ni_win).model_dump(),
            roe_mean=_opt(roe_mean),
            roe_min=float(roe.min()) if roe.size else None,
            roe_std=_opt(roe_std),
            op_margin_mean=_opt(mgn_mean),
            op_margin_std=_opt(mgn_std),
            net_income_cv=_opt(coefficient_of_variation(net_income)) if net_income.size else None,
            loss_years=int((net_income < 0).sum()) if net_income.size else None,
        )


class BalanceSheet(CalcNode):
    """Leverage and coverage at the latest period, each field falling back to an older one if needed.

    Each field comes from the newest of the last `MAX_STALE_PERIODS + 1` periods holding all of
    its inputs (one row per field, so a ratio never mixes periods); a field from an older period
    is listed in `field_periods`. The window spans from the oldest row used to the latest period,
    as in `FundamentalTrend`.
    """

    name: ClassVar[str] = "balance_sheet"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"annual": "annual_fundamentals"}
    output: ClassVar = BalanceSheetResult
    code_deps: ClassVar = (safe_ratio, _ratio_on, _latest_point, latest_complete, _opt, *_WINDOW_DEPS)

    def run(self, ctx: NodeContext, annual: pd.DataFrame) -> BalanceSheetResult:
        """Compute debt-to-equity, interest cover and net debt from their newest complete periods."""
        rows, stale, window = _latest_point(
            annual,
            {
                "debt_to_equity": ("total_debt", "common_equity"),
                "interest_cover": ("operating_income", "interest_expense"),
                "net_debt": ("total_debt", "cash"),
            },
        )
        debt = rows["net_debt"]
        return BalanceSheetResult(
            **window.model_dump(exclude={"field_periods"}),
            debt_to_equity=_opt(_ratio_on(rows["debt_to_equity"], "total_debt", "common_equity")),
            interest_cover=_opt(
                _ratio_on(rows["interest_cover"], "operating_income", "interest_expense")
            ),
            net_debt=float(_col(debt, "total_debt")[0] - _col(debt, "cash")[0]) if len(debt) else None,
            field_periods=stale,
        )


class CashGeneration(CalcNode):
    """Owner earnings and FCF at the latest period, FCF conversion and share-count trend over the window.

    Owner earnings and FCF each fall back to the newest of the last `MAX_STALE_PERIODS + 1`
    periods holding all their inputs and are listed in `field_periods` when older. The reported
    window spans from the oldest row any field used (FCF conversion, share count, owner earnings,
    FCF) to the latest period, like `BalanceSheet`.
    """

    name: ClassVar[str] = "cash_generation"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"annual": "annual_fundamentals"}
    output: ClassVar = CashGenerationResult
    code_deps: ClassVar = (
        owner_earnings,
        sum_ratio,
        cagr,
        _fcf,
        years_between,
        _latest_point,
        latest_complete,
        _span,
        _opt,
        *_WINDOW_DEPS,
    )

    def run(self, ctx: NodeContext, annual: pd.DataFrame) -> CashGenerationResult:
        """Compute the cash-generation fields over `annual`."""
        rows, stale, latest_win = _latest_point(
            annual, {"owner_earnings": _OE_COLUMNS, "fcf": ("operating_cash_flow", "capex")}
        )
        oe_rows, fcf_rows = rows["owner_earnings"], rows["fcf"]
        conv_rows, conv_win = values(annual, "operating_cash_flow", "capex", "net_income")
        share_rows, share_win = values(annual, "shares_diluted")
        oe = (
            _opt(float(owner_earnings(*(_col(oe_rows, c) for c in _OE_COLUMNS))[0]))
            if len(oe_rows)
            else None
        )
        fcf = _opt(float(_fcf(fcf_rows)[0])) if len(fcf_rows) else None
        conversion = (
            sum_ratio(_fcf(conv_rows), _col(conv_rows, "net_income"))
            if len(conv_rows)
            else float("nan")
        )
        share_cagr = float("nan")
        if len(share_rows) >= 2:
            ends = share_rows["period_end"]
            years = years_between(ends.iloc[0], ends.iloc[-1])
            shares = _col(share_rows, "shares_diluted")
            share_cagr = cagr(float(shares[0]), float(shares[-1]), years)
        window = _span(annual, conv_win, share_win, latest_win)
        # safeguard: list only fields older than the reported window's end (drops nothing now)
        older = {n: d for n, d in stale.items() if window.last_period_end and d < window.last_period_end}
        return CashGenerationResult(
            **window.model_dump(exclude={"field_periods"}),
            owner_earnings=oe,
            fcf=fcf,
            fcf_conversion=_opt(conversion),
            share_count_cagr=_opt(share_cagr),
            field_periods=older,
        )


class FundamentalTrend(CalcNode):
    """Year-on-year and 3-year growth and margin change, measured on actual period dates.

    The "1y" fields compare the latest period with the one before and are None when their
    `period_end`s are more than 18 months apart (a provider gap or fiscal-year change), so a
    missing year never silently stretches the span. `revenue_cagr_3y` compares the latest
    period with the period whose `period_end` is closest to three years earlier (within 6
    months; else None) and compounds over the actual years between the two `period_end`s,
    the same span helper (`years_between`) `share_count_cagr` uses. The window is the periods
    from the earliest one used to the latest.
    """

    name: ClassVar[str] = "fundamental_trend"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"annual": "annual_fundamentals"}
    output: ClassVar = FundamentalTrendResult
    code_deps: ClassVar = (growth, cagr, safe_ratio, _fcf, years_between, _opt, *_WINDOW_DEPS)

    def run(self, ctx: NodeContext, annual: pd.DataFrame) -> FundamentalTrendResult:
        """Compute growth fields from the latest period against the previous one and the one ~3 years back."""
        prev = len(annual) - 2 if len(annual) >= 2 else None
        base3 = _base_three_years_back(annual)
        earliest = min((i for i in (prev, base3) if i is not None), default=len(annual) - 1)
        revenue = _series(annual, "revenue")
        fcf = _fcf(annual) if len(annual) else np.array([])
        one_year = {"annual": annual, "base": prev, "max_years": _MAX_STEP_YEARS}
        return FundamentalTrendResult(
            **period_window(annual.iloc[max(earliest, 0) :]).model_dump(),
            revenue_growth_1y=_change(series=revenue, fn=lambda a, b, y: growth(a, b), **one_year),
            revenue_cagr_3y=_change(annual, revenue, base3, cagr),
            op_margin_change_1y=_change(
                series=_margin(annual), fn=lambda a, b, y: b - a, **one_year
            ),
            eps_growth_1y=_change(series=_eps(annual), fn=lambda a, b, y: growth(a, b), **one_year),
            fcf_growth_1y=_change(series=fcf, fn=lambda a, b, y: growth(a, b), **one_year),
        )


def _base_three_years_back(annual: pd.DataFrame) -> int | None:
    """Position of the earlier period closest to three years before the latest, or None if none within 6 months."""
    if len(annual) < 2:
        return None
    ends = annual["period_end"]
    target = ends.iloc[-1] - pd.DateOffset(years=_TREND_YEARS)
    gaps = (ends.iloc[:-1] - target).abs()
    best = int(gaps.to_numpy().argmin())
    return best if gaps.iloc[best].days <= _BASE_TOLERANCE_DAYS else None


def _series(annual: pd.DataFrame, column: str) -> np.ndarray:
    """`column` per period as a float array, `nan` for missing periods (positions stay aligned)."""
    return annual[column].to_numpy(float)


def _margin(annual: pd.DataFrame) -> np.ndarray:
    """Operating margin per period, `nan` where an input is missing or revenue <= 0."""
    return _paired(annual, "operating_income", "revenue", safe_ratio)


def _eps(annual: pd.DataFrame) -> np.ndarray:
    """EPS (`net_income / shares_diluted`) per period; `nan` where an input is missing."""
    return _paired(annual, "net_income", "shares_diluted", safe_ratio)


def _paired(
    annual: pd.DataFrame, num: str, den: str, fn: Callable[[np.ndarray, np.ndarray], np.ndarray]
) -> np.ndarray:
    """Apply the kernel `fn(num, den)` on periods with both present; `nan` elsewhere."""
    out = np.full(len(annual), np.nan)
    ok = annual[num].notna().to_numpy() & annual[den].notna().to_numpy()
    if ok.any():
        out[ok] = fn(
            _col(cast(pd.DataFrame, annual[ok]), num), _col(cast(pd.DataFrame, annual[ok]), den)
        )
    return out


def _change(
    annual: pd.DataFrame,
    series: np.ndarray,
    base: int | None,
    fn: Callable[[float, float, float], float],
    max_years: float | None = None,
) -> float | None:
    """`fn(value at base, latest value, years between their period_ends)`.

    None when there is no base period, either value is missing, or the span exceeds `max_years`.
    """
    if base is None:
        return None
    ends = annual["period_end"]
    years = years_between(ends.iloc[base], ends.iloc[-1])
    prev, cur = series[base], series[-1]
    if (max_years is not None and years > max_years) or np.isnan(prev) or np.isnan(cur):
        return None
    return _opt(fn(float(prev), float(cur), years))
