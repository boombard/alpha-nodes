"""SEC XBRL company facts: the stored raw payload, the curated tag map, and the mapping to `fundamentals`.

The only code that knows `us-gaap` tag names and the shape of the company-facts JSON. See
documentation/design/finance.md, Fundamentals: datasets, providers and pinned conventions (Providers
and Checks on `fundamentals` rows).
"""

from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel

COMPANYFACTS_NORMALISER_VERSION = "1"
"""Bump when `normalise_companyfacts` or `TAG_MAP` change behaviour; the store then renormalises."""


class EdgarFactsPayload(BaseModel):
    """The verbatim company-facts JSON for one symbol; stored as the raw payload.

    Facts are rebuilt from this on renormalise (core.md, Source store).

    Args:
        symbol: the Yahoo symbol the entity was asked for.
        cik: SEC Central Index Key the ticker mapped to.
        facts: the company-facts document as served (`{"cik", "entityName", "facts": {"us-gaap": ...}}`).
    """

    symbol: str
    cik: int
    facts: dict[str, Any]


class ItemTags(BaseModel, frozen=True):
    """The `us-gaap` tags of one canonical line item, split by what a difference between them means.

    Args:
        synonyms: the same quantity under different names or eras (e.g. the ASC 606 revenue tag replacing
            `SalesRevenueNet`). The first with a value wins; a later synonym with a value more than 1% away
            marks the row `suspect` (`tag_conflict:<item>`).
        fallbacks: a different scope of the quantity (a wider or narrower measure, often from another
            statement or note). Used only when no synonym has a value, never compared, and the row's
            `repairs` records which one supplied it (`fallback:<item>=<tag>`).
    """

    synonyms: tuple[str, ...]
    fallbacks: tuple[str, ...] = ()

    @property
    def all(self) -> tuple[str, ...]:
        """Every tag of the item, synonyms first."""
        return (*self.synonyms, *self.fallbacks)


TAG_MAP: dict[str, ItemTags] = {
    # Flow items (annual duration). `Revenues` is total revenue including leasing and finance income (which is
    # why Boeing and GE differed from the ASC 606 tag); `SalesRevenueNet` is its pre-2018 name. The ASC 606
    # tags (contract revenue only) and `SalesRevenueGoodsNet` (goods only, Coca-Cola until 2016) are narrower
    # scopes, so fallbacks: ASC 606-only filers such as Apple after 2018 get `fallback:revenue=...` in repairs.
    "revenue": ItemTags(
        synonyms=("Revenues", "SalesRevenueNet"),
        fallbacks=(
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueGoodsNet",
        ),
    ),
    # Alternatives considered: IncomeLossFromContinuingOperationsBeforeIncomeTaxes... (pre-tax, not operating).
    "operating_income": ItemTags(synonyms=("OperatingIncomeLoss",)),
    # Attributable to the parent. After-preferred-dividends is a different measure, so a fallback.
    "net_income": ItemTags(
        synonyms=("NetIncomeLoss",), fallbacks=("NetIncomeLossAvailableToCommonStockholdersBasic",)
    ),
    # Alternatives considered: InterestPaid (cash, not expense), InterestAndDebtExpense (wider).
    # InterestExpenseDebt excludes non-debt interest, so a fallback.
    "interest_expense": ItemTags(
        synonyms=("InterestExpense", "InterestExpenseNonoperating"), fallbacks=("InterestExpenseDebt",)
    ),
    # The cash-flow add-back is the primary; the note/segment variants are different measures.
    "depreciation_amortization": ItemTags(
        synonyms=("DepreciationDepletionAndAmortization",),
        fallbacks=("DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"),
    ),
    "operating_cash_flow": ItemTags(
        synonyms=("NetCashProvidedByUsedInOperatingActivities",),
        fallbacks=("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",),
    ),
    # Reported as a cash outflow (positive payment); stored positive. ProductiveAssets is wider.
    # Alternatives: PaymentsToAcquireOtherPropertyPlantAndEquipment.
    "capex": ItemTags(
        synonyms=("PaymentsToAcquirePropertyPlantAndEquipment",),
        fallbacks=("PaymentsToAcquireProductiveAssets",),
    ),
    # Instant items (balance sheet, period end).
    "total_assets": ItemTags(synonyms=("Assets",)),
    # Some filers (e.g. Coca-Cola) never tag Liabilities. Where total_equity is the NCI-inclusive figure it is
    # derived as LiabilitiesAndStockholdersEquity - total_equity (`derived:total_liabilities`); otherwise null,
    # since minority interest would be counted as a liability.
    "total_liabilities": ItemTags(synonyms=("Liabilities",)),
    # Including minority interest first; StockholdersEquity (excluding it) is the fallback.
    "total_equity": ItemTags(
        synonyms=("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",),
        fallbacks=("StockholdersEquity",),
    ),
    "common_equity": ItemTags(synonyms=("StockholdersEquity",)),
    # Total borrowings, composed by `_compose_total_debt`: long-term debt incl. current maturities
    # (`LongTermDebt`, else a non-current figure + DebtCurrent or + its current portion and short-term
    # borrowings, all fallbacks), or the all-in `DebtAndCapitalLeaseObligations` alone. Finance leases are included on the CapitalLease paths;
    # operating lease liabilities are excluded.
    "total_debt": ItemTags(
        synonyms=("LongTermDebt",),
        fallbacks=(
            "LongTermDebtNoncurrent",
            "LongTermDebtCurrent",
            "DebtCurrent",
            "LongTermDebtAndCapitalLeaseObligations",
            "LongTermDebtAndCapitalLeaseObligationsCurrent",
            "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
            "DebtAndCapitalLeaseObligations",
            "ShortTermBorrowings",
            "CommercialPaper",
        ),
    ),
    "cash": ItemTags(
        synonyms=("CashAndCashEquivalentsAtCarryingValue",),
        fallbacks=("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",),
    ),
    # Weighted average (flow, unit `shares`).
    "shares_diluted": ItemTags(synonyms=("WeightedAverageNumberOfDilutedSharesOutstanding",)),
    # Period-end count (instant, unit `shares`). When untagged (Coca-Cola) `_fill_shares_outstanding` uses
    # CommonStockSharesIssued - treasury shares, else the dei cover-page count of the same filing (a few
    # weeks after the period end, so only a last resort, recorded in `repairs`).
    "shares_outstanding": ItemTags(synonyms=("CommonStockSharesOutstanding",)),
}
"""Canonical line item -> its `us-gaap` tags, as synonyms (priority order) and fallbacks (see `ItemTags`)."""

_SHARE_ITEMS = frozenset({"shares_diluted", "shares_outstanding"})
_INSTANT_ITEMS = frozenset(
    {"total_assets", "total_liabilities", "total_equity", "common_equity", "total_debt", "cash", "shares_outstanding"}
)
_FORMS = frozenset({"10-K", "10-K/A"})
_MIN_DAYS, _MAX_DAYS = 350, 380
_CONFLICT_TOLERANCE = 0.01
_BALANCE_TOLERANCE = 0.02

_ITEMS = tuple(TAG_MAP)
_STATIC_COLUMNS = ("period_type", "period_end", "filed_at", "currency")
_META_COLUMNS = ("repairs", "quality", "quality_reasons", "known_at")


def _empty_frame() -> pd.DataFrame:
    """A zero-row frame with every canonical and meta column, correctly typed."""
    return pd.DataFrame(
        {
            "period_type": pd.Series(dtype="object"),
            "period_end": pd.Series(dtype="datetime64[ns]"),
            "filed_at": pd.Series(dtype="datetime64[ns]"),
            "currency": pd.Series(dtype="object"),
            **{item: pd.Series(dtype="float64") for item in _ITEMS},
            "repairs": pd.Series(dtype="object"),
            "quality": pd.Series(dtype="object"),
            "quality_reasons": pd.Series(dtype="object"),
            "known_at": pd.Series(dtype="datetime64[ns, UTC]"),
        }
    )


def _qualifying_facts(item: str, entry: dict[str, Any]) -> list[tuple[date, date, float]]:
    """(period_end, filed, value) of the annual 10-K facts of one tag, in the item's unit.

    Flow items need a start date and a 350-380 day duration (drops quarterly and year-to-date facts a
    10-K also carries); instant items must have no start. Facts in other units are ignored.
    """
    unit = "shares" if item in _SHARE_ITEMS else "USD"
    out: list[tuple[date, date, float]] = []
    for fact in entry.get("units", {}).get(unit, []):
        if fact.get("form") not in _FORMS or fact.get("fp") != "FY" or fact.get("val") is None:
            continue
        start = fact.get("start")
        if item in _INSTANT_ITEMS:
            if start is not None:
                continue
        else:
            if start is None:
                continue
            days = (date.fromisoformat(fact["end"]) - date.fromisoformat(start)).days
            if not _MIN_DAYS <= days <= _MAX_DAYS:
                continue
        out.append((date.fromisoformat(fact["end"]), date.fromisoformat(fact["filed"]), float(fact["val"])))
    return out


def _tag_values(item: str, us_gaap: dict[str, Any], tag: str) -> dict[tuple[date, date], float]:
    """(period_end, filed) -> value of one extra tag, qualified like the item `item` (unit, instant or flow)."""
    return {(end, filed): val for end, filed, val in _qualifying_facts(item, us_gaap.get(tag, {}))}


def _differs(first: float, other: float) -> bool:
    """True when `other` is more than 1% away from `first`."""
    return abs(other - first) > _CONFLICT_TOLERANCE * abs(first)


def _pick(item: str, values: dict[str, float]) -> tuple[float, list[str], list[str]]:
    """Value of one item for one (period, filing): (value, repairs, reasons).

    The first synonym with a value wins and a later synonym more than 1% away gives `tag_conflict:<item>`;
    with no synonym the first fallback with a value is used (never compared) and recorded as
    `fallback:<item>=<tag>`. NaN when nothing is tagged.
    """
    tags = TAG_MAP[item]
    synonyms = [t for t in tags.synonyms if t in values]
    if synonyms:
        first = values[synonyms[0]]
        conflict = any(_differs(first, values[t]) for t in synonyms[1:])
        return first, [], [f"tag_conflict:{item}"] if conflict else []
    for tag in tags.fallbacks:
        if tag in values:
            return values[tag], [f"fallback:{item}={tag}"], []
    return float("nan"), [], []


def _compose_total_debt(values: dict[str, float]) -> tuple[float, list[str], list[str]]:
    """Total borrowings of one (period, filing) from its debt tag values: (value, repairs, reasons).

    The first matching path wins; a complete composition always beats a partial one. Every path but the
    first is recorded in `repairs` as `fallback:total_debt=<tags>`. `cap` is
    `LongTermDebtAndCapitalLeaseObligations` (non-current), `current` the first tagged of `cap`+`Current`,
    `LongTermDebtCurrent`, and `short` the first tagged of `ShortTermBorrowings`, `CommercialPaper` (0 if none).

    1. `LongTermDebt` (includes current maturities) + short.
    2. `LongTermDebtNoncurrent` + `DebtCurrent` (all current debt: short-term borrowings, commercial paper
       and current maturities), nothing else added.
    3. `LongTermDebtNoncurrent` + `LongTermDebtCurrent` + short.
    4. `cap` + `DebtCurrent`, nothing else added.
    5. `cap` + `current` + short.
    6. `cap`'s `...IncludingCurrentMaturities` twin + short (used after the plain tag: Chevron tags its
       non-current figure under both names).
    7. `DebtAndCapitalLeaseObligations` alone (already includes current and short-term debt).
    8. Partial: `LongTermDebtNoncurrent` + short, with reason `partial:total_debt`.
    9. Partial: `cap` + short, with reason `partial:total_debt`.

    `DebtCurrent` is deliberately not used on paths 1 and 6, whose long-term figure already includes the
    current maturities. NaN when none is tagged. Finance leases are included on the `cap` paths; operating
    lease liabilities never are. See finance.md, Providers (EDGAR).
    """
    cap = "LongTermDebtAndCapitalLeaseObligations"
    short = next((values[t] for t in ("ShortTermBorrowings", "CommercialPaper") if t in values), 0.0)
    if "LongTermDebt" in values:
        return values["LongTermDebt"] + short, [], []
    for base, current_tags in (
        ("LongTermDebtNoncurrent", ("LongTermDebtCurrent",)),
        (cap, (f"{cap}Current", "LongTermDebtCurrent")),
    ):
        if base in values and "DebtCurrent" in values:
            return values[base] + values["DebtCurrent"], [f"fallback:total_debt={base}+DebtCurrent"], []
        current = next((t for t in current_tags if t in values), None)
        if base in values and current is not None:
            return values[base] + values[current] + short, [f"fallback:total_debt={base}+{current}"], []
    twin = f"{cap}IncludingCurrentMaturities"
    if twin in values:
        return values[twin] + short, [f"fallback:total_debt={twin}"], []
    if "DebtAndCapitalLeaseObligations" in values:
        return values["DebtAndCapitalLeaseObligations"], ["fallback:total_debt=DebtAndCapitalLeaseObligations"], []
    for base in ("LongTermDebtNoncurrent", cap):
        if base in values:
            return values[base] + short, [f"fallback:total_debt={base}"], ["partial:total_debt"]
    return float("nan"), [], []


_TREASURY_TAGS = ("TreasuryStockCommonShares", "TreasuryStockShares")
_COVER_WINDOW_DAYS = 150
"""A dei cover-page count belongs to a period end at most this many days before the cover date."""


def _dei_cover_counts(facts: dict[str, Any]) -> dict[tuple[date, date], set[float]]:
    """dei cover-page share counts of the 10-K filings: (cover date, filed) -> the distinct values.

    More than one value for one filing means several share classes (companyfacts drops the class
    dimension), which cannot be summed or picked safely.
    """
    rows = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {})
    out: dict[tuple[date, date], set[float]] = {}
    for fact in rows.get("units", {}).get("shares", []):
        if fact.get("form") in _FORMS and fact.get("val") is not None:
            key = (date.fromisoformat(fact["end"]), date.fromisoformat(fact["filed"]))
            out.setdefault(key, set()).add(float(fact["val"]))
    return out


def _fill_shares_outstanding(
    end: date,
    filed: date,
    issued: float | None,
    treasury: float | None,
    cover: dict[tuple[date, date], set[float]],
) -> tuple[float, list[str], list[str]]:
    """Period-end shares when `CommonStockSharesOutstanding` is untagged: (value, repairs, reasons).

    In order: `CommonStockSharesIssued` - treasury shares at the same period end (`derived:shares_outstanding=
    issued-treasury`; treasury missing skips this step, it is never assumed 0); else the dei cover-page count
    of the same filing when its date is 0-150 days after the period end and it is the only value
    (`fallback:shares_outstanding=dei_cover`); with several values (share classes) the count stays NaN and
    the row gets reason `multi_class:shares_outstanding` (quality unchanged).
    """
    if issued is not None and treasury is not None:
        return issued - treasury, ["derived:shares_outstanding=issued-treasury"], []
    counts = {
        v
        for (cover_date, cover_filed), vals in cover.items()
        if cover_filed == filed and 0 <= (cover_date - end).days <= _COVER_WINDOW_DAYS
        for v in vals
    }
    if len(counts) == 1:
        return next(iter(counts)), ["fallback:shares_outstanding=dei_cover"], []
    if len(counts) > 1:
        return float("nan"), [], ["multi_class:shares_outstanding"]
    return float("nan"), [], []


def normalise_companyfacts(payload: EdgarFactsPayload) -> pd.DataFrame:
    """Map company facts to `FundamentalsSchema` rows plus the `NormalisedMeta` columns.

    One row per (period_end, filed_at): a later 10-K re-reporting a period gives its own row, so as-of
    queries see what was filed by then. Only forms 10-K and 10-K/A with fp "FY" count, flow items need a
    350-380 day duration, and a row exists only where some flow item has a full-year fact (so
    cover-page and equity-statement dates do not become periods). Per item the first synonym tag in
    `TAG_MAP` with a value is used and a later synonym differing by more than 1% marks the row `suspect`
    (`tag_conflict:<item>`); fallback tags (a different scope) are used only when no synonym has a value,
    never compared, and recorded in the row's `repairs` as `fallback:<item>=<tag>`. `total_assets` vs `total_liabilities +
    total_equity` more than 2% apart marks it `suspect` (`balance_mismatch`). `total_debt` is composed by
    `_compose_total_debt` rather than first-tag-wins. Two gaps are filled by identities, recorded in `repairs`:
    `total_liabilities` = `LiabilitiesAndStockholdersEquity` - `total_equity` when `Liabilities` is untagged
    and `total_equity` is the NCI-inclusive tag (`derived:total_liabilities`), and `shares_outstanding` via
    `_fill_shares_outstanding`. Capex is stored positive;
    currency is "USD" and facts in other units are ignored. `known_at` is `filed_at` (UTC midnight).
    Returns an empty typed frame when there are no us-gaap annual facts.
    """
    us_gaap: dict[str, Any] = payload.facts.get("facts", {}).get("us-gaap", {})
    # item -> (period_end, filed) -> {tag: value}
    found: dict[str, dict[tuple[date, date], dict[str, float]]] = {}
    for item, tags in TAG_MAP.items():
        by_key: dict[tuple[date, date], dict[str, float]] = {}
        for tag in tags.all:
            for end, filed, val in _qualifying_facts(item, us_gaap.get(tag, {})):
                by_key.setdefault((end, filed), {})[tag] = val
        found[item] = by_key
    liabilities_and_equity = _tag_values("total_assets", us_gaap, "LiabilitiesAndStockholdersEquity")
    issued = _tag_values("shares_outstanding", us_gaap, "CommonStockSharesIssued")
    treasury = [_tag_values("shares_outstanding", us_gaap, tag) for tag in _TREASURY_TAGS]
    cover = _dei_cover_counts(payload.facts)
    periods = sorted({key for item in _ITEMS if item not in _INSTANT_ITEMS | _SHARE_ITEMS for key in found[item]})
    if not periods:
        return _empty_frame()
    rows: list[dict[str, Any]] = []
    for end, filed in periods:
        row: dict[str, Any] = {
            "period_type": "annual",
            "period_end": pd.Timestamp(end),
            "filed_at": pd.Timestamp(filed),
            "currency": "USD",
        }
        reasons: list[str] = []
        repairs: list[str] = []
        for item in _ITEMS:
            values = found[item].get((end, filed), {})
            if item == "total_debt":
                row[item], item_repairs, item_reasons = _compose_total_debt(values)
            else:
                row[item], item_repairs, item_reasons = _pick(item, values)
                if item == "capex":
                    row[item] = abs(row[item])
            repairs.extend(item_repairs)
            reasons.extend(item_reasons)
        if pd.isna(row["total_liabilities"]) and (end, filed) in liabilities_and_equity:
            nci_equity = not pd.isna(row["total_equity"]) and not any(r.startswith("fallback:total_equity") for r in repairs)
            if nci_equity:
                row["total_liabilities"] = liabilities_and_equity[(end, filed)] - row["total_equity"]
                repairs.append("derived:total_liabilities")
        if pd.isna(row["shares_outstanding"]):
            row["shares_outstanding"], fill_repairs, fill_reasons = _fill_shares_outstanding(
                end,
                filed,
                issued.get((end, filed)),
                next((t[(end, filed)] for t in treasury if (end, filed) in t), None),
                cover,
            )
            repairs.extend(fill_repairs)
            reasons.extend(fill_reasons)
        assets, liabilities, equity = row["total_assets"], row["total_liabilities"], row["total_equity"]
        known = not (pd.isna(assets) or pd.isna(liabilities) or pd.isna(equity))
        if known and abs(assets - (liabilities + equity)) > _BALANCE_TOLERANCE * abs(assets):
            reasons.append("balance_mismatch")
        row["repairs"] = repairs
        row["quality"] = "suspect" if any(not r.startswith("multi_class:") for r in reasons) else "ok"
        row["quality_reasons"] = reasons
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame["period_end"] = frame["period_end"].astype("datetime64[ns]")
    frame["filed_at"] = frame["filed_at"].astype("datetime64[ns]")
    frame["known_at"] = frame["filed_at"].dt.tz_localize("UTC").astype("datetime64[ns, UTC]")
    return pd.DataFrame(frame[[*_STATIC_COLUMNS, *_ITEMS, *_META_COLUMNS]])
