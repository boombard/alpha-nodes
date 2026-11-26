"""EDGAR company-facts normalisation: recorded AAPL/KO facts, and constructed payloads for the rules."""

from typing import Any

import pandas as pd
import pytest
from alpha_nodes.datasets import FundamentalsSchema
from alpha_nodes.providers.edgar.companyfacts import (
    TAG_MAP,
    EdgarFactsPayload,
    normalise_companyfacts,
)

from .edgar_replay import load_payload

CORE_ITEMS = ["revenue", "net_income", "common_equity", "operating_cash_flow"]


def _row(end: str, val: float, *, start: str | None = "2023-01-01", filed: str = "2024-02-15",
         accn: str = "A1", form: str = "10-K", fp: str = "FY") -> dict[str, Any]:
    row: dict[str, Any] = {"end": end, "val": val, "accn": accn, "fy": 2023, "fp": fp, "form": form, "filed": filed}
    if start is not None:
        row["start"] = start
    return row


def _payload(
    facts: dict[str, list[dict[str, Any]]],
    unit: str = "USD",
    shares: dict[str, list[dict[str, Any]]] | None = None,
    dei_shares: list[dict[str, Any]] | None = None,
) -> EdgarFactsPayload:
    """A synthetic payload: tag -> rows in `unit`, `shares` tags in unit "shares", and dei cover counts."""
    us_gaap = {tag: {"units": {unit: rows}} for tag, rows in facts.items()}
    us_gaap.update({tag: {"units": {"shares": rows}} for tag, rows in (shares or {}).items()})
    dei = {"EntityCommonStockSharesOutstanding": {"units": {"shares": dei_shares or []}}}
    return EdgarFactsPayload(symbol="TST", cik=1, facts={"facts": {"us-gaap": us_gaap, "dei": dei}})


def _annual(tag_values: dict[str, float], **kw: Any) -> dict[str, list[dict[str, Any]]]:
    """One FY2023 annual row per tag; instants (balance sheet) get no start."""
    instants = {"DebtCurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "DebtAndCapitalLeaseObligations", "LiabilitiesAndStockholdersEquity", "LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "CommercialPaper", "Assets", "Liabilities", "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"}
    return {
        tag: [_row("2023-12-31", val, start=None if tag in instants else "2023-01-01", **kw)]
        for tag, val in tag_values.items()
    }


@pytest.fixture(scope="module")
def aapl() -> pd.DataFrame:
    return normalise_companyfacts(load_payload("AAPL"))


@pytest.fixture(scope="module")
def ko() -> pd.DataFrame:
    return normalise_companyfacts(load_payload("KO"))


def test_aapl_annual_periods_have_canonical_items(aapl: pd.DataFrame) -> None:
    assert len(set(aapl["period_end"])) >= 8
    latest = aapl.sort_values(["period_end", "filed_at"]).iloc[-1]
    for item in CORE_ITEMS:
        assert not bool(pd.isna(latest[item])), item
    assert bool((aapl["currency"] == "USD").all()) and bool((aapl["period_type"] == "annual").all())
    FundamentalsSchema.validate(pd.DataFrame(aapl[list(FundamentalsSchema.to_schema().columns)]))


def test_known_at_is_filed_at(aapl: pd.DataFrame) -> None:
    assert bool((aapl["known_at"] == aapl["filed_at"].dt.tz_localize("UTC")).all())
    assert str(aapl["known_at"].dtype) == "datetime64[ns, UTC]"


def test_comparatives_from_later_10k_are_separate_rows(aapl: pd.DataFrame) -> None:
    per_period = aapl.groupby("period_end")["filed_at"].nunique()
    assert max(per_period) >= 2
    assert not bool(aapl.duplicated(["period_end", "filed_at"]).any())


def test_capex_is_positive(aapl: pd.DataFrame, ko: pd.DataFrame) -> None:
    for frame in (aapl, ko):
        assert bool(frame["capex"].notna().any()) and bool((frame["capex"].dropna() >= 0).all())


def test_balance_check_passes_on_aapl(aapl: pd.DataFrame) -> None:
    reasons = {r for rs in aapl["quality_reasons"] for r in rs}
    assert "balance_mismatch" not in reasons
    assert bool(aapl["total_liabilities"].notna().any())


def test_ko_december_fiscal_year(ko: pd.DataFrame) -> None:
    assert bool((ko["period_end"].dt.month == 12).all())
    assert len(set(ko["period_end"])) >= 8


def test_tag_conflict_marks_suspect() -> None:
    facts = _annual({"Revenues": 1000.0, "SalesRevenueNet": 1100.0})
    frame = normalise_companyfacts(_payload(facts))
    assert len(frame) == 1 and frame["revenue"].iloc[0] == 1000.0  # priority order wins
    assert frame["quality"].iloc[0] == "suspect"
    assert "tag_conflict:revenue" in frame["quality_reasons"].iloc[0]


def test_tags_within_one_percent_do_not_conflict() -> None:
    facts = _annual({"Revenues": 1000.0, "SalesRevenueNet": 1005.0})
    assert normalise_companyfacts(_payload(facts))["quality"].iloc[0] == "ok"


def test_balance_mismatch_marks_suspect() -> None:
    facts = _annual({"Revenues": 1000.0, "Assets": 1000.0, "Liabilities": 600.0,
                     "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": 300.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["quality"].iloc[0] == "suspect" and "balance_mismatch" in frame["quality_reasons"].iloc[0]


def test_quarterly_and_short_duration_facts_ignored() -> None:
    facts = {
        "Revenues": [
            _row("2023-12-31", 250.0, start="2023-10-01"),  # a 10-K's fourth quarter
            _row("2023-12-31", 900.0, start="2023-01-01", accn="A2", fp="Q3", form="10-Q"),
        ]
    }
    assert normalise_companyfacts(_payload(facts)).empty


def test_non_usd_facts_are_ignored() -> None:
    assert normalise_companyfacts(_payload(_annual({"Revenues": 1000.0}), unit="EUR")).empty


def test_10k_amendment_adds_a_later_filing_row() -> None:
    facts = _annual({"Revenues": 1000.0})
    facts["Revenues"].append(_row("2023-12-31", 990.0, filed="2024-06-01", accn="A2", form="10-K/A"))
    frame = normalise_companyfacts(_payload(facts)).sort_values("filed_at")
    assert list(frame["filed_at"]) == [pd.Timestamp("2024-02-15"), pd.Timestamp("2024-06-01")]
    assert list(frame["revenue"]) == [1000.0, 990.0]


def test_no_usgaap_annual_facts_gives_empty_frame() -> None:
    frame = normalise_companyfacts(EdgarFactsPayload(symbol="TST", cik=1, facts={"facts": {"ifrs-full": {}}}))
    assert frame.empty
    assert {"revenue", "known_at", "quality", "quality_reasons", "repairs"} <= set(frame.columns)


def test_tag_map_lists_every_canonical_flow_and_stock_item() -> None:
    assert set(TAG_MAP) == set(FundamentalsSchema.to_schema().columns) - {
        "period_type", "period_end", "filed_at", "currency",
    }


def _total_debt(tags: dict[str, float]) -> tuple[float, list[str]]:
    frame = normalise_companyfacts(_payload(_annual({"Revenues": 1.0, **tags})))
    return frame["total_debt"].iloc[0], frame["quality_reasons"].iloc[0]


def test_total_debt_sums_long_term_and_commercial_paper() -> None:
    assert _total_debt({"LongTermDebt": 100.0, "CommercialPaper": 7.0}) == (107.0, [])
    assert _total_debt({"LongTermDebt": 100.0}) == (100.0, [])  # no short-term borrowings tagged: 0
    assert _total_debt({"LongTermDebt": 100.0, "ShortTermBorrowings": 5.0, "CommercialPaper": 7.0})[0] == 105.0


def test_total_debt_noncurrent_plus_current_fallback() -> None:
    assert _total_debt({"LongTermDebtNoncurrent": 90.0, "LongTermDebtCurrent": 10.0}) == (100.0, [])


def test_total_debt_noncurrent_only_is_partial_and_suspect() -> None:
    value, reasons = _total_debt({"LongTermDebtNoncurrent": 90.0, "CommercialPaper": 5.0})
    assert value == 95.0 and reasons == ["partial:total_debt"]
    frame = normalise_companyfacts(_payload(_annual({"Revenues": 1.0, "LongTermDebtNoncurrent": 90.0})))
    assert frame["quality"].iloc[0] == "suspect"


def test_total_debt_missing_without_long_term_debt() -> None:
    assert pd.isna(_total_debt({"CommercialPaper": 5.0})[0])


def test_aapl_total_debt_includes_commercial_paper(aapl: pd.DataFrame) -> None:
    facts = load_payload("AAPL").facts["facts"]["us-gaap"]["LongTermDebt"]["units"]["USD"]
    latest = max((f for f in facts if f["form"] == "10-K"), key=lambda f: (f["end"], f["filed"]))
    row = aapl[(aapl["period_end"] == pd.Timestamp(latest["end"])) & (aapl["filed_at"] == pd.Timestamp(latest["filed"]))]
    assert float(next(iter(row["total_debt"]))) > latest["val"]


NCI_EQUITY = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"


def test_fallback_differing_from_primary_is_not_suspect() -> None:
    facts = _annual({"Revenues": 1.0, "DepreciationDepletionAndAmortization": 100.0, "DepreciationAndAmortization": 140.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["depreciation_amortization"].iloc[0] == 100.0
    assert frame["quality"].iloc[0] == "ok" and frame["repairs"].iloc[0] == []


def test_fallback_used_when_primary_missing_and_recorded_in_repairs() -> None:
    facts = _annual({"Revenues": 1.0, "DepreciationAndAmortization": 140.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["depreciation_amortization"].iloc[0] == 140.0
    assert frame["repairs"].iloc[0] == ["fallback:depreciation_amortization=DepreciationAndAmortization"]
    assert frame["quality"].iloc[0] == "ok"


def test_total_debt_composition_paths_are_recorded_in_repairs() -> None:
    _, plain = _total_debt({"LongTermDebt": 100.0})
    assert plain == []
    facts = _annual({"Revenues": 1.0, "LongTermDebtNoncurrent": 90.0, "LongTermDebtCurrent": 10.0})
    assert normalise_companyfacts(_payload(facts))["repairs"].iloc[0] == [
        "fallback:total_debt=LongTermDebtNoncurrent+LongTermDebtCurrent"
    ]
    facts = _annual({"Revenues": 1.0, "LongTermDebtNoncurrent": 90.0})
    assert normalise_companyfacts(_payload(facts))["repairs"].iloc[0] == ["fallback:total_debt=LongTermDebtNoncurrent"]


def test_aapl_and_lake_depreciation_and_interest_are_not_tag_conflicts(aapl: pd.DataFrame) -> None:
    for frame in (aapl, normalise_companyfacts(load_payload("LAKE"))):
        reasons = {r for rs in frame["quality_reasons"] for r in rs}
        assert not {"tag_conflict:depreciation_amortization", "tag_conflict:interest_expense"} & reasons


def test_total_liabilities_derived_with_nci_inclusive_equity() -> None:
    facts = _annual({"Revenues": 1.0, "Assets": 1000.0, NCI_EQUITY: 300.0, "LiabilitiesAndStockholdersEquity": 1000.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_liabilities"].iloc[0] == 700.0
    assert "derived:total_liabilities" in frame["repairs"].iloc[0] and frame["quality"].iloc[0] == "ok"


def test_total_liabilities_not_derived_with_stockholders_equity_only() -> None:
    facts = _annual({"Revenues": 1.0, "Assets": 1000.0, "StockholdersEquity": 300.0, "LiabilitiesAndStockholdersEquity": 1000.0})
    frame = normalise_companyfacts(_payload(facts))
    assert pd.isna(frame["total_liabilities"].iloc[0]) and "derived:total_liabilities" not in frame["repairs"].iloc[0]


def _shares_frame(
    shares: dict[str, float], dei: list[tuple[str, float]] | None = None, filed: str = "2024-02-15"
) -> pd.DataFrame:
    rows = {tag: [_row("2023-12-31", val, start=None)] for tag, val in shares.items()}
    cover = [_row(end, val, start=None, filed=filed) for end, val in (dei or [])]
    return normalise_companyfacts(_payload(_annual({"Revenues": 1.0}), shares=rows, dei_shares=cover))


def test_shares_outstanding_issued_minus_treasury() -> None:
    frame = _shares_frame({"CommonStockSharesIssued": 100.0, "TreasuryStockShares": 30.0})
    assert frame["shares_outstanding"].iloc[0] == 70.0
    assert frame["repairs"].iloc[0] == ["derived:shares_outstanding=issued-treasury"]
    assert _shares_frame({"CommonStockSharesIssued": 100.0, "TreasuryStockCommonShares": 20.0, "TreasuryStockShares": 30.0})[
        "shares_outstanding"
    ].iloc[0] == 80.0  # TreasuryStockCommonShares first


def test_shares_outstanding_tagged_value_wins_over_derivation() -> None:
    frame = _shares_frame({"CommonStockSharesOutstanding": 65.0, "CommonStockSharesIssued": 100.0, "TreasuryStockShares": 30.0})
    assert frame["shares_outstanding"].iloc[0] == 65.0 and frame["repairs"].iloc[0] == []


def test_shares_outstanding_missing_treasury_is_not_assumed_zero() -> None:
    assert pd.isna(_shares_frame({"CommonStockSharesIssued": 100.0})["shares_outstanding"].iloc[0])


def test_shares_outstanding_dei_cover_fallback_with_one_value() -> None:
    frame = _shares_frame({}, dei=[("2024-02-10", 55.0)])
    assert frame["shares_outstanding"].iloc[0] == 55.0
    assert frame["repairs"].iloc[0] == ["fallback:shares_outstanding=dei_cover"] and frame["quality"].iloc[0] == "ok"


def test_shares_outstanding_multi_class_dei_left_null_without_suspect() -> None:
    frame = _shares_frame({}, dei=[("2024-02-10", 55.0), ("2024-02-10", 20.0)])
    assert pd.isna(frame["shares_outstanding"].iloc[0])
    assert frame["quality"].iloc[0] == "ok" and frame["quality_reasons"].iloc[0] == ["multi_class:shares_outstanding"]


def test_ko_latest_row_has_liabilities_and_shares(ko: pd.DataFrame) -> None:
    latest = ko.sort_values(["period_end", "filed_at"]).iloc[-1]
    assert latest["total_liabilities"] > 0 and latest["shares_outstanding"] > 1e9
    assert latest["quality"] == "ok"  # the balance check ran and passed
    assert {"derived:total_liabilities", "derived:shares_outstanding=issued-treasury"} <= set(latest["repairs"])


ASC606 = "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_revenues_vs_asc606_tag_is_not_a_conflict() -> None:
    frame = normalise_companyfacts(_payload(_annual({"Revenues": 1000.0, ASC606: 700.0})))
    assert frame["revenue"].iloc[0] == 1000.0 and frame["quality"].iloc[0] == "ok"


def test_asc606_only_filer_uses_fallback_and_is_not_suspect() -> None:
    frame = normalise_companyfacts(_payload(_annual({ASC606: 700.0})))
    assert frame["revenue"].iloc[0] == 700.0 and frame["quality"].iloc[0] == "ok"
    assert frame["repairs"].iloc[0] == [f"fallback:revenue={ASC606}"]


def test_aapl_post_2018_revenue_is_a_recorded_asc606_fallback(aapl: pd.DataFrame) -> None:
    latest = aapl.sort_values(["period_end", "filed_at"]).iloc[-1]
    assert f"fallback:revenue={ASC606}" in latest["repairs"] and latest["quality"] == "ok"


CAP = "LongTermDebtAndCapitalLeaseObligations"


def test_total_debt_capital_lease_path_with_each_current_tag() -> None:
    assert _total_debt({CAP: 90.0, f"{CAP}Current": 10.0, "LongTermDebtCurrent": 99.0, "CommercialPaper": 5.0}) == (105.0, [])
    facts = _annual({"Revenues": 1.0, CAP: 90.0, "LongTermDebtCurrent": 10.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_debt"].iloc[0] == 100.0 and frame["repairs"].iloc[0] == [f"fallback:total_debt={CAP}+LongTermDebtCurrent"]
    facts = _annual({"Revenues": 1.0, CAP: 90.0, f"{CAP}Current": 10.0})
    assert normalise_companyfacts(_payload(facts))["repairs"].iloc[0] == [f"fallback:total_debt={CAP}+{CAP}Current"]


def test_total_debt_capital_lease_path_without_current_is_partial() -> None:
    facts = _annual({"Revenues": 1.0, CAP: 90.0, "ShortTermBorrowings": 4.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_debt"].iloc[0] == 94.0 and frame["quality"].iloc[0] == "suspect"
    assert frame["quality_reasons"].iloc[0] == ["partial:total_debt"] and frame["repairs"].iloc[0] == [f"fallback:total_debt={CAP}"]


def test_total_debt_including_current_maturities_taken_directly() -> None:
    facts = _annual({"Revenues": 1.0, f"{CAP}IncludingCurrentMaturities": 100.0, "LongTermDebtCurrent": 10.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_debt"].iloc[0] == 100.0 and frame["quality"].iloc[0] == "ok"
    assert frame["repairs"].iloc[0] == [f"fallback:total_debt={CAP}IncludingCurrentMaturities"]


def test_total_debt_all_in_tag_alone_without_short_term_borrowings() -> None:
    facts = _annual({"Revenues": 1.0, "DebtAndCapitalLeaseObligations": 120.0, "ShortTermBorrowings": 20.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_debt"].iloc[0] == 120.0 and frame["quality"].iloc[0] == "ok"
    assert frame["repairs"].iloc[0] == ["fallback:total_debt=DebtAndCapitalLeaseObligations"]


def test_ko_latest_total_debt_is_present(ko: pd.DataFrame) -> None:
    latest = ko.sort_values(["period_end", "filed_at"]).iloc[-1]
    assert latest["total_debt"] > 4e10  # 42.1bn long-term + 1.8bn current + 1.5bn commercial paper


def test_total_debt_noncurrent_plus_debt_current_adds_nothing_else() -> None:
    facts = _annual({"Revenues": 1.0, "LongTermDebtNoncurrent": 90.0, "DebtCurrent": 15.0, "LongTermDebtCurrent": 10.0,
                     "ShortTermBorrowings": 3.0, "CommercialPaper": 2.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_debt"].iloc[0] == 105.0 and frame["quality"].iloc[0] == "ok"
    assert frame["repairs"].iloc[0] == ["fallback:total_debt=LongTermDebtNoncurrent+DebtCurrent"]


def test_total_debt_capital_lease_plus_debt_current() -> None:
    facts = _annual({"Revenues": 1.0, CAP: 90.0, "DebtCurrent": 15.0, "CommercialPaper": 2.0, "LongTermDebtCurrent": 10.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_debt"].iloc[0] == 105.0 and frame["repairs"].iloc[0] == [f"fallback:total_debt={CAP}+DebtCurrent"]
    assert frame["quality_reasons"].iloc[0] == []


def test_complete_capital_lease_path_beats_noncurrent_alone() -> None:
    facts = _annual({"Revenues": 1.0, "LongTermDebtNoncurrent": 80.0, CAP: 90.0, f"{CAP}Current": 10.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_debt"].iloc[0] == 100.0 and frame["quality"].iloc[0] == "ok"
    assert frame["repairs"].iloc[0] == [f"fallback:total_debt={CAP}+{CAP}Current"]
    facts = _annual({"Revenues": 1.0, "LongTermDebtNoncurrent": 80.0, CAP: 90.0, "DebtCurrent": 5.0})
    assert normalise_companyfacts(_payload(facts))["total_debt"].iloc[0] == 85.0  # Noncurrent family first


def test_total_debt_debt_current_ignored_with_long_term_debt() -> None:
    facts = _annual({"Revenues": 1.0, "LongTermDebt": 100.0, "DebtCurrent": 15.0, "CommercialPaper": 2.0})
    frame = normalise_companyfacts(_payload(facts))
    assert frame["total_debt"].iloc[0] == 102.0 and frame["repairs"].iloc[0] == []
    twin = _annual({"Revenues": 1.0, f"{CAP}IncludingCurrentMaturities": 100.0, "DebtCurrent": 15.0})
    assert normalise_companyfacts(_payload(twin))["total_debt"].iloc[0] == 100.0


def test_total_debt_unchanged_where_longtermdebt_is_tagged(aapl: pd.DataFrame) -> None:
    facts = load_payload("AAPL").facts["facts"]["us-gaap"]
    lt = {(f["end"], f["filed"]): f["val"] for f in facts["LongTermDebt"]["units"]["USD"] if f["form"] == "10-K"}
    cp = {(f["end"], f["filed"]): f["val"] for f in facts.get("CommercialPaper", {}).get("units", {}).get("USD", [])}
    for (end, filed), value in lt.items():
        row = aapl[(aapl["period_end"] == pd.Timestamp(end)) & (aapl["filed_at"] == pd.Timestamp(filed))]
        if len(row) and (end, filed) not in cp:
            assert next(iter(row["total_debt"])) == value
