---
id: TASK-54
title: M6.7 Valuation calcs with fx-converted market cap
status: To Do
assignee: []
created_date: '2026-11-25T08:17:59Z'
labels:
  - finance
milestone: m-5
dependencies:
  - TASK-53
  - TASK-61
references:
  - documentation/design/finance.md
type: feature
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Valuation calcs that combine price-side and statement-side money: market cap through `fx`, owner-earnings yield, the intrinsic-value band, P/E and its change over a year. After M6.6 (they reuse its adapters). Spec: `documentation/design/finance.md` ("Fundamentals: ... pinned conventions": Market cap, Valuation, Valuation change; Currency; Prices and point-in-time).

## Files
- Create:
  - `packages/alpha_nodes/src/alpha_nodes/valuation.py`: adapter `valuation_on`
  - `packages/alpha_nodes/src/alpha_nodes/nodes/valuation_calcs.py`
- Modify: `packages/alpha_nodes/src/alpha_nodes/series.py` (add `close_on`, `bars_back`)
- Test: `packages/alpha_nodes/tests/test_valuation.py`, `packages/alpha_nodes/tests/test_valuation_calcs.py`, `packages/alpha_nodes/tests/test_series.py`
- Modify `documentation/design/finance.md` only if behaviour differs from it.

## Interfaces
Consumes: `annual_periods`, `period_window` (M6.6); `latest_complete`, `PeriodWindow.field_periods`, `MAX_STALE_PERIODS` (TASK-61); `reference_day`, `fx_factor`, `ValuationResult`, `ValuationChangeResult`, `BARS_PER_YEAR` (M6.1, M5); kernels `owner_earnings`, `capitalised_value`, `safe_ratio` (M6.2); the `prices` frame (M4) and the `fx` frame from `FxRates` (entity column).

Produces:
```python
# series.py
def close_on(prices: pd.DataFrame, day: date) -> tuple[date, float, str] | None   # last bar on or before day: (date, close, currency)
def bars_back(prices: pd.DataFrame, day: date, bars: int) -> date | None          # the bar date `bars` sessions before the last bar on or before day

# valuation.py
def valuation_on(prices: pd.DataFrame, fundamentals: pd.DataFrame, fx: pd.DataFrame, day: date,
                 hurdle_low: float = 0.08, hurdle_high: float = 0.12) -> ValuationResult
    # periods = annual_periods(fundamentals, day); shares_outstanding, net_income and owner earnings each via
    # latest_complete (TASK-61), recording any older period in field_periods;
    # market_cap = close × shares × fx_factor(trading -> reporting, price_date); a missing fx rate -> fx_rate None and
    # every money-derived field None (never a silent 1.0); value_low = OE / hurdle_high, value_high = OE / hurdle_low

# nodes/valuation_calcs.py   (memoize=False, code_deps)
class Valuation(CalcNode):       name = "valuation"
    inputs = {"prices": "prices", "fundamentals": "fundamentals", "fx": "fx"}; output = ValuationResult
    hurdle_low: float = 0.08; hurdle_high: float = 0.12        # validator: 0 < hurdle_low < hurdle_high
class ValuationChange(CalcNode): name = "valuation_change"
    inputs = {"prices": "prices", "fundamentals": "fundamentals", "fx": "fx"}; output = ValuationChangeResult
    lookback_bars: int = BARS_PER_YEAR
    # now = reference_day(ctx); then = bars_back(prices, now, lookback_bars); each side uses the periods known on its own day
```
Both read the raw `fundamentals` frame (not `annual_fundamentals`) so the "then" side sees the filings known then, not later restatements.

## Steps
- [ ] Write the failing tests (hand-built frames; fx frames with an `entity` column):
  - `test_series.py`: `test_close_on_takes_last_bar_on_or_before`, `test_close_on_none_before_first_bar`, `test_bars_back`.
  - `test_valuation.py`: `test_same_currency_hand_values` (USD/USD: market cap, earnings yield, P/E, OE yield, band, price_to_value), `test_cross_currency_uses_fx` (GBP trading, USD reporting: fx_rate = usd_per_unit(GBP)), `test_missing_fx_rate_gives_none_not_one`, `test_negative_earnings_pe_none_yield_negative`, `test_negative_owner_earnings_band_none`, `test_no_known_periods_gives_zero_period_result`, `test_valuation_records_stale_shares_in_field_periods` (latest row lacks shares_outstanding: shares from the year before, listed in field_periods).
  - `test_valuation_calcs.py`: `test_valuation_change_uses_periods_known_then` (a period filed between then and now is used only for now), `test_valuation_change_pe_change_hand_value`, `test_short_price_history_then_none`, `test_hurdles_validated`, `test_valuation_nodes_are_not_memoized_and_declare_code_deps`.
- [ ] Run `uv run pytest packages/alpha_nodes/tests/test_valuation.py packages/alpha_nodes/tests/test_valuation_calcs.py packages/alpha_nodes/tests/test_series.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): valuation calcs with fx-converted market cap`.

Out of scope: EV/EBIT (needs debt and cash at the price date; later); as-of warnings for level-based calcs (M8); registering nodes (M6.10).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Valuation and ValuationChange exist as specified; market cap converts trading to reporting currency through fx on the price date
- [ ] #2 A missing fx rate gives None money fields, never a silent 1.0; negative earnings give pe None
- [ ] #3 ValuationChange uses the periods known on each side's own day
- [ ] #4 close_on and bars_back added to series.py with tests
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
