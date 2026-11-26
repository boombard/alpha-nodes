"""Tests for the fundamentals calc nodes (`alpha_nodes.nodes.fundamental_calcs`); values are hand-computed."""

import statistics
from collections.abc import Callable
from datetime import date

import pandas as pd
import pytest
from alpha_nodes import statements
from alpha_nodes.kernels import (
    cagr,
    coefficient_of_variation,
    growth,
    mean_std,
    owner_earnings,
    safe_ratio,
    sum_ratio,
)
from alpha_nodes.metrics import ProfitabilityResult
from alpha_nodes.nodes.fundamental_calcs import (
    AnnualFundamentals,
    BalanceSheet,
    CashGeneration,
    FundamentalTrend,
    Profitability,
)
from lensgraph.node import NodeContext
from lensgraph.types import CandidateRef

Rows = Callable[..., pd.DataFrame]
DAY = date(2030, 1, 1)
NODES = (AnnualFundamentals, Profitability, BalanceSheet, CashGeneration, FundamentalTrend)


@pytest.fixture
def ctx() -> NodeContext:
    return NodeContext(run_id="r", candidate=CandidateRef(id="BP.L"), as_of=DAY)


@pytest.fixture
def annual(fundamentals_rows: Rows) -> Callable[..., pd.DataFrame]:
    """Factory: `annual(*rows)` is the `annual_fundamentals` frame; row `i` is the year-end of 2020 + i."""

    def make(*rows: dict) -> pd.DataFrame:
        full = [{"period_end": f"{2020 + i}-12-31", **row} for i, row in enumerate(rows)]
        return statements.annual_periods(fundamentals_rows(*full), DAY)

    return make


def test_annual_fundamentals_node_uses_reference_day(
    ctx: NodeContext, fundamentals_rows: Rows
) -> None:
    frame = fundamentals_rows(
        {"period_end": "2020-12-31"}, {"period_end": "2029-12-31"}
    )  # 2nd known 2030-03-30
    out = AnnualFundamentals().run(ctx, fundamentals=frame)
    assert [d.year for d in out["period_end"]] == [2020]
    assert (
        len(
            AnnualFundamentals(max_periods=1).run(
                ctx,
                fundamentals=fundamentals_rows(
                    {"period_end": "2020-12-31"}, {"period_end": "2021-12-31"}
                ),
            )
        )
        == 1
    )


def test_profitability_hand_values(ctx: NodeContext, annual: Callable[..., pd.DataFrame]) -> None:
    # ROE .10 .12 .10 .10 ; margin .10 .12 .10 .15 ; net income 10 12 15 20
    frame = annual(
        {"net_income": 10.0, "common_equity": 100.0, "revenue": 100.0, "operating_income": 10.0},
        {"net_income": 12.0, "common_equity": 100.0, "revenue": 100.0, "operating_income": 12.0},
        {"net_income": 15.0, "common_equity": 150.0, "revenue": 100.0, "operating_income": 10.0},
        {"net_income": 20.0, "common_equity": 200.0, "revenue": 100.0, "operating_income": 15.0},
    )
    out = Profitability().run(ctx, annual=frame)
    assert out.roe_mean == pytest.approx(0.105)
    assert out.roe_min == pytest.approx(0.10)
    assert out.roe_std == pytest.approx(0.01)  # sqrt(3e-4 / 3)
    assert out.op_margin_mean == pytest.approx(0.1175)
    assert out.op_margin_std == pytest.approx(statistics.stdev([0.10, 0.12, 0.10, 0.15]))
    assert out.net_income_cv == pytest.approx(statistics.stdev([10, 12, 15, 20]) / 14.25)
    assert out.loss_years == 0
    assert (out.periods, out.currency, out.last_period_end) == (4, "GBP", date(2023, 12, 31))

    lossy = annual({"net_income": 10.0}, {"net_income": -5.0}, {"net_income": 15.0})
    out = Profitability().run(ctx, annual=lossy)
    assert out.loss_years == 1
    assert out.net_income_cv == pytest.approx(statistics.stdev([10, -5, 15]) / (20 / 3))


def test_roe_none_for_nonpositive_equity_period(
    ctx: NodeContext, annual: Callable[..., pd.DataFrame]
) -> None:
    frame = annual(
        {"net_income": 10.0, "common_equity": 100.0},
        {"net_income": 5.0, "common_equity": -50.0},
        {"net_income": 30.0, "common_equity": 100.0},
    )
    out = Profitability().run(ctx, annual=frame)
    assert out.roe_mean == pytest.approx(0.2)  # the negative-equity period is skipped, not zeroed
    assert out.roe_min == pytest.approx(0.1)
    assert out.roe_std is None  # two usable periods < 3


def test_balance_sheet_hand_values(ctx: NodeContext, annual: Callable[..., pd.DataFrame]) -> None:
    frame = annual(
        {"total_debt": 999.0, "common_equity": 1.0},
        {
            "total_debt": 300.0,
            "common_equity": 200.0,
            "operating_income": 60.0,
            "interest_expense": 20.0,
            "cash": 50.0,
        },
    )
    out = BalanceSheet().run(ctx, annual=frame)
    assert out.debt_to_equity == pytest.approx(1.5)
    assert out.interest_cover == pytest.approx(3.0)
    assert out.net_debt == pytest.approx(250.0)
    assert out.periods == 1  # latest period only
    assert out.last_period_end == date(2021, 12, 31)


def test_interest_cover_none_without_interest(
    ctx: NodeContext, annual: Callable[..., pd.DataFrame]
) -> None:
    missing = annual({"operating_income": 60.0, "total_debt": 10.0, "common_equity": -5.0})
    out = BalanceSheet().run(ctx, annual=missing)
    assert (out.interest_cover, out.debt_to_equity, out.net_debt) == (None, None, None)
    zero = annual({"operating_income": 60.0, "interest_expense": 0.0})
    assert BalanceSheet().run(ctx, annual=zero).interest_cover is None


def test_cash_generation_hand_values(ctx: NodeContext, annual: Callable[..., pd.DataFrame]) -> None:
    base = {"depreciation_amortization": 5.0}
    frame = annual(
        {
            **base,
            "net_income": 10.0,
            "operating_cash_flow": 20.0,
            "capex": 4.0,
            "shares_diluted": 100.0,
        },
        {
            **base,
            "net_income": 30.0,
            "operating_cash_flow": 40.0,
            "capex": 8.0,
            "shares_diluted": 110.0,
        },
        {
            **base,
            "net_income": 20.0,
            "operating_cash_flow": 30.0,
            "capex": 3.0,
            "shares_diluted": 121.0,
        },
    )
    out = CashGeneration().run(ctx, annual=frame)
    assert out.owner_earnings == pytest.approx(22.0)  # capex 3 < D&A 5: 20 + 5 - 3
    assert out.fcf == pytest.approx(27.0)
    assert out.fcf_conversion == pytest.approx((16 + 32 + 27) / 60)
    years = (date(2022, 12, 31) - date(2020, 12, 31)).days / 365.25
    assert out.share_count_cagr == pytest.approx(1.21 ** (1 / years) - 1)
    assert out.periods == 3

    above = annual({**base, "net_income": 20.0, "operating_cash_flow": 30.0, "capex": 8.0})
    assert CashGeneration().run(ctx, annual=above).owner_earnings == pytest.approx(
        20.0
    )  # capex capped at D&A


def test_cash_generation_none_without_items(
    ctx: NodeContext, annual: Callable[..., pd.DataFrame]
) -> None:
    out = CashGeneration().run(ctx, annual=annual({"net_income": 10.0}))
    assert (out.owner_earnings, out.fcf, out.fcf_conversion, out.share_count_cagr) == (
        None,
        None,
        None,
        None,
    )


def test_fundamental_trend_hand_values(
    ctx: NodeContext, annual: Callable[..., pd.DataFrame]
) -> None:
    frame = annual(
        {
            "revenue": 100.0,
            "operating_income": 10.0,
            "net_income": 8.0,
            "shares_diluted": 10.0,
            "operating_cash_flow": 5.0,
            "capex": 15.0,
        },
        {
            "revenue": 110.0,
            "operating_income": 11.0,
            "net_income": 9.0,
            "shares_diluted": 10.0,
            "operating_cash_flow": 5.0,
            "capex": 5.0,
        },
        {
            "revenue": 120.0,
            "operating_income": 12.0,
            "net_income": 10.0,
            "shares_diluted": 10.0,
            "operating_cash_flow": 10.0,
            "capex": 5.0,
        },
        {
            "revenue": 133.1,
            "operating_income": 20.0,
            "net_income": 12.0,
            "shares_diluted": 8.0,
            "operating_cash_flow": 15.0,
            "capex": 5.0,
        },
    )
    out = FundamentalTrend().run(ctx, annual=frame)
    assert out.revenue_growth_1y == pytest.approx(133.1 / 120 - 1)
    assert out.revenue_cagr_3y == pytest.approx(
        1.331 ** (365.25 / 1095) - 1
    )  # actual span: 1095 days
    assert out.op_margin_change_1y == pytest.approx(20 / 133.1 - 0.1)
    assert out.eps_growth_1y == pytest.approx(1.5 / 1.0 - 1)  # EPS 1.0 -> 1.5
    assert out.fcf_growth_1y == pytest.approx(1.0)  # FCF 5 -> 10
    assert out.periods == 4


def test_fcf_growth_from_negative_base(
    ctx: NodeContext, annual: Callable[..., pd.DataFrame]
) -> None:
    frame = annual(
        {"operating_cash_flow": 0.0, "capex": 10.0},  # FCF -10
        {"operating_cash_flow": 15.0, "capex": 10.0},  # FCF +5
    )
    assert FundamentalTrend().run(ctx, annual=frame).fcf_growth_1y == pytest.approx(
        1.5
    )  # (5 + 10) / |-10|


def test_trend_none_with_one_period(ctx: NodeContext, annual: Callable[..., pd.DataFrame]) -> None:
    out = FundamentalTrend().run(ctx, annual=annual({"revenue": 100.0, "operating_income": 10.0}))
    assert out.periods == 1
    assert out.model_dump(
        exclude={"periods", "first_period_end", "last_period_end", "suspect_periods", "currency"}
    ) == {
        "revenue_growth_1y": None,
        "revenue_cagr_3y": None,
        "op_margin_change_1y": None,
        "eps_growth_1y": None,
        "fcf_growth_1y": None,
    }


def test_bank_without_operating_items_gives_none_margins(
    ctx: NodeContext, annual: Callable[..., pd.DataFrame]
) -> None:
    frame = annual(*({"net_income": 10.0 + i, "common_equity": 100.0} for i in range(3)))
    prof = Profitability().run(ctx, annual=frame)
    assert (prof.op_margin_mean, prof.op_margin_std) == (None, None)
    assert prof.roe_mean is not None
    assert FundamentalTrend().run(ctx, annual=frame).op_margin_change_1y is None


def test_empty_fundamentals_give_zero_period_results(
    ctx: NodeContext, annual: Callable[..., pd.DataFrame]
) -> None:
    empty = annual()
    for node in (Profitability, BalanceSheet, CashGeneration, FundamentalTrend):
        out = node().run(ctx, annual=empty)
        assert (out.periods, out.first_period_end, out.last_period_end, out.currency) == (
            0,
            None,
            None,
            None,
        )
        fields = out.model_dump(
            exclude={
                "periods",
                "first_period_end",
                "last_period_end",
                "suspect_periods",
                "currency",
            }
        )
        assert all(v is None for v in fields.values())
    assert isinstance(Profitability().run(ctx, annual=empty), ProfitabilityResult)


def test_calc_nodes_declare_their_kernels() -> None:
    assert {safe_ratio, mean_std, coefficient_of_variation, statements.values} <= set(
        Profitability.code_deps
    )
    assert {safe_ratio, statements.values} <= set(BalanceSheet.code_deps)
    assert {owner_earnings, sum_ratio, cagr, statements.values} <= set(CashGeneration.code_deps)
    assert {growth, cagr, statements.values} <= set(FundamentalTrend.code_deps)
    assert {statements.annual_periods, statements.known_on} <= set(AnnualFundamentals.code_deps)


def test_fundamental_calc_nodes_are_not_memoized() -> None:
    assert [n.memoize for n in NODES] == [False] * 5


def _trend_rows(fundamentals_rows: Rows, years: list[int]) -> pd.DataFrame:
    """Annual frame for the given fiscal years: revenue 100, 110, ... and FCF 10 + 10 * i."""
    rows = [
        {
            "period_end": f"{y}-12-31",
            "revenue": 100.0 + 10 * i,
            "operating_income": 10.0 + i,
            "net_income": 5.0 + i,
            "shares_diluted": 10.0,
            "operating_cash_flow": 20.0 + 10 * i,
            "capex": 10.0,
        }
        for i, y in enumerate(years)
    ]
    return statements.annual_periods(fundamentals_rows(*rows), DAY)


def test_trend_handles_missing_fiscal_year(ctx: NodeContext, fundamentals_rows: Rows) -> None:
    frame = _trend_rows(fundamentals_rows, [2019, 2020, 2022, 2023])  # revenue 100 110 120 130
    out = FundamentalTrend().run(ctx, annual=frame)
    assert out.revenue_growth_1y == pytest.approx(130 / 120 - 1)  # 2022 -> 2023
    assert out.fcf_growth_1y == pytest.approx(40 / 30 - 1)  # FCF 30 -> 40
    assert out.eps_growth_1y == pytest.approx((8 / 10) / (7 / 10) - 1)
    assert out.op_margin_change_1y == pytest.approx(13 / 130 - 12 / 120)
    years = (date(2023, 12, 31) - date(2020, 12, 31)).days / 365.25
    assert out.revenue_cagr_3y == pytest.approx(
        (130 / 110) ** (1 / years) - 1
    )  # 2020 base, not 2019
    assert out.first_period_end == date(2020, 12, 31)
    assert out.periods == 3


def test_trend_one_year_steps_none_when_latest_periods_two_years_apart(
    ctx: NodeContext, fundamentals_rows: Rows
) -> None:
    frame = _trend_rows(fundamentals_rows, [2020, 2021, 2023])
    out = FundamentalTrend().run(ctx, annual=frame)
    assert out.revenue_growth_1y is None
    assert out.op_margin_change_1y is None
    assert out.eps_growth_1y is None
    assert out.fcf_growth_1y is None
    assert out.revenue_cagr_3y is not None  # 2020 -> 2023 is still a 3-year span


def test_trend_cagr_none_without_period_near_three_years_back(
    ctx: NodeContext, fundamentals_rows: Rows
) -> None:
    frame = _trend_rows(
        fundamentals_rows, [2018, 2021, 2023]
    )  # 2020 is 3y back: 2021 is 12 months off
    out = FundamentalTrend().run(ctx, annual=frame)
    assert out.revenue_cagr_3y is None
    assert out.revenue_growth_1y is None  # 2021 -> 2023 is two years
