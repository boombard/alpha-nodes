---
id: TASK-29
title: >-
  M4.4 alpha_nodes scaffold: canonical prices, profile and fx datasets, units
  and exchange calendars
status: In Progress
assignee: []
created_date: '2026-11-25T01:09:16Z'
updated_date: '2026-11-25T02:53:29Z'
labels:
  - finance
milestone: m-3
dependencies:
  - TASK-26
references:
  - documentation/design/core.md
  - documentation/design/finance.md
type: feature
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create the `alpha_nodes` package: canonical `prices`, `profile` and `fx` datasets (provider-neutral), unit/currency helpers, and exchange calendars. Parallel with M4.2 and M4.3. Spec: `documentation/design/finance.md` (market focus, Datasets, Data quality principles 1–2, Prices and point-in-time, Currency), and the provider-abstraction rule: nothing here knows yfinance names or Yahoo ticker suffixes.

Planning decisions (2026-11-25; update finance.md in this task):
- **No adjusted close in `prices`.** Store close (as the provider gives it), dividends and split ratio. Yahoo's adjusted close rewrites the past on every dividend, which breaks append-only facts. The total-return adjustment is our own calc node (M5).
- **No market cap in `profile`.** Store shares outstanding; market cap = price × shares is computed (principle 1).

## Files
- Create:
  - `packages/alpha_nodes/pyproject.toml`: name `alpha-nodes`, deps `lensgraph`, `exchange_calendars` (pin a current version)
  - `packages/alpha_nodes/src/alpha_nodes/__init__.py`
  - `packages/alpha_nodes/src/alpha_nodes/datasets.py`: schemas and `Dataset`s
  - `packages/alpha_nodes/src/alpha_nodes/units.py`: field kinds, minor units, ISO currency check
  - `packages/alpha_nodes/src/alpha_nodes/markets.py`: exchange calendars and settled cut-off
  - `packages/alpha_nodes/tests/conftest.py`
- Modify:
  - root `pyproject.toml`: `[tool.uv.sources] alpha-nodes = { workspace = true }`, add `alpha-nodes` to the dev group, add `packages/alpha_nodes/tests` to pytest `pythonpath` (test helpers like `yf_replay` are imported by name)
  - `documentation/design/finance.md`: the two decisions above (Datasets table, Prices and point-in-time)
- Test: `packages/alpha_nodes/tests/{test_datasets,test_units,test_markets}.py`

## Interfaces
Consumes: `Dataset` (M4.1).

Produces:
```python
# units.py
FieldKind = Literal["money", "per_share", "shares", "ratio", "count", "date", "text", "code"]
MINOR_UNITS: dict[str, tuple[str, int]]   # {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ZAc": ("ZAR", 100), "ILA": ("ILS", 100)}
def to_major(currency: str) -> tuple[str, int]      # ("GBP", 100) for "GBp"; ("EUR", 1) for "EUR"; ValueError for junk
def is_major_iso(code: str) -> bool                 # three upper-case letters and not a minor-unit code
# datasets.py  (every column declares its kind via pa.Field(metadata={"kind": ...}))
class PriceSchema(pa.DataFrameModel):   # one row per trading day, major units
    date: datetime64 (tz-naive midnight = exchange-local trading date)
    open, high, low, close: float > 0 (money)
    volume: Int64 >= 0, nullable (count)
    dividends: float >= 0 (per_share; 0.0 when none)
    split_ratio: float > 0 (ratio; 1.0 when none)
    currency: str, is_major_iso (code)
class ProfileSchema(pa.DataFrameModel):  # one row per entity
    name: str; isin: str nullable; exchange: str (MIC, e.g. "XLON"); country: str nullable
    trading_currency: str (major ISO); reporting_currency: str nullable (major ISO)
    sector: str nullable; industry: str nullable
    shares_outstanding: float nullable > 0 (shares); listing_date: datetime64 nullable
    business_summary: str nullable
class FxSchema(pa.DataFrameModel):      # entity = currency code, e.g. "GBP"
    date: datetime64; usd_per_unit: float > 0 (ratio)
PRICES: Dataset   # axis "date" on "date", key ("date",), ttl 1 day, empty_ttl 7 days
PROFILE: Dataset  # axis "none", key (), ttl 90 days, empty_ttl 7 days
FX: Dataset       # axis "date" on "date", key ("date",), ttl 1 day, empty_ttl 7 days
DATASETS: dict[str, Dataset]
# markets.py
MICS: frozenset[str]   # XLON XPAR XAMS XBRU XLIS XDUB XETR XMIL XMAD XSWX XSTO XCSE XOSL XHEL XNYS XNAS
SETTLE_DELAY = timedelta(minutes=30)
def is_session(mic: str, day: date) -> bool
def sessions(mic: str, start: date, end: date) -> list[date]
def session_close(mic: str, day: date) -> datetime          # tz-aware UTC; ValueError if not a session
def settled_through(mic: str, now: datetime) -> date | None # last session whose close + SETTLE_DELAY <= now
def fx_settled_through(now: datetime) -> date               # FX trades round the clock: the previous UTC day
```
Map MICs to `exchange_calendars` names inside `markets.py` (XNAS shares XNYS's calendar). An unknown MIC is a `ValueError` naming it.

## Steps
- [ ] Write the failing tests:
  - `test_units.py`: `test_to_major_minor_units`, `test_to_major_rejects_junk`, `test_is_major_iso`.
  - `test_datasets.py`:
    - `test_every_column_declares_a_kind` (all three schemas)
    - `test_prices_reject_minor_unit_currency`: a frame with `currency="GBp"` fails validation.
    - `test_prices_reject_non_positive_close`
    - `test_profile_allows_missing_optionals`
    - `test_datasets_registry_names_match`
  - `test_markets.py`:
    - `test_settled_before_and_after_close`: XLON on a Wednesday at 15:00 UTC → previous session; at close + 31 min → that day.
    - `test_settled_over_weekend_and_holiday`: Saturday → Friday; 2026-12-28 (UK bank holiday) handled.
    - `test_settled_per_exchange_timezone`: XETR and XNYS on the same instant give different answers where the closes differ.
    - `test_fx_settled_is_previous_utc_day`
    - `test_unknown_mic_raises`
- [ ] Run `uv run pytest packages/alpha_nodes -q`. Expected: FAIL.
- [ ] Implement; `uv sync`; update finance.md.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): package scaffold, canonical prices/profile/fx datasets, exchange calendars`.

Out of scope: any provider (M4.6, M4.7), fetch nodes (M4.9).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 alpha_nodes package is a uv workspace member and its tests run under uv run pytest
- [ ] #2 PriceSchema, ProfileSchema and FxSchema declare a kind per column and reject minor-unit currencies; PRICES, PROFILE and FX datasets exist
- [ ] #3 markets.settled_through applies close + 30 min per exchange calendar, weekends and holidays; FX settles at the previous UTC day
- [ ] #4 finance.md records: no adjusted close in prices, no market cap in profile
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_8554a93cd1c0, worktree task-29
<!-- SECTION:NOTES:END -->
