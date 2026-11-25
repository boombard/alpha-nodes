---
id: TASK-37
title: >-
  M4.7b yfinance prices and fx hardening: transient empties, settled tail, more
  checks, error classes
status: To Do
assignee: []
created_date: '2026-11-25T04:06:45Z'
labels:
  - finance
milestone: m-3
dependencies:
  - TASK-32
  - TASK-36
references:
  - documentation/design/finance.md
type: feature
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Hardening of `YFinanceProvider` for prices and fx, from the 2026-11-25 defensive review: stop transient Yahoo glitches from becoming permanent covered holes, catch wrong values the current checks miss, and classify systemic failures so the core breakers (TASK-36) can stop a run. After M4.7 (TASK-32: its small-cap fixtures inform the gap threshold; it also edits `provider.py`) and TASK-36 (policy fields). Spec: `documentation/design/finance.md`, "yfinance fetching and throttling" and "Data quality: yfinance quirks"; update both in this change (the quirks table gets a row per new check).

The rule behind most of this: the store is append-only and never refetches a range coverage holds, so whatever a single response says is kept forever. A response that is probably a glitch must be `error` (not cached), never `ok`.

## Files
- Modify:
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/provider.py`: classification, settled cap, truncation check, `YF_POLICY`
  - `packages/alpha_nodes/src/alpha_nodes/providers/yfinance/history.py`: duplicate bars, new checks, normaliser versions
  - `packages/alpha_nodes/pyproject.toml`: pin `curl_cffi` to the version in `uv.lock` (`==`); `uv.lock` if it changes
  - `documentation/design/finance.md`
- Test: `packages/alpha_nodes/tests/test_yf_provider.py`, `packages/alpha_nodes/tests/test_yf_history.py`

## Interfaces
Consumes: M4.6/M4.7 provider, `YFHistoryPayload`, fixtures and conftest loaders; `markets.*`; `RateLimitPolicy.max_consecutive_errors/max_consecutive_empty` (TASK-36).

Produces: no new public names beyond constants in `history.py` (thresholds, documented). `PRICES_NORMALISER_VERSION` and `FX_NORMALISER_VERSION` become `"2"`.

Semantics, provider (`provider.py`):
1. `YFPricesMissingError` for a symbol whose timezone is known: `ok` with an empty payload **only when** the exchange calendar has no sessions in the requested interval (weekend, holiday); otherwise `error` ("no bars for a range with N sessions"), so it is retried and never cached. Accepted cost: a delisted ticker topped up past its last bar raises `SourceUnavailable` on each run; delisting is M7/M8 work. Unknown timezone stays `empty`.
2. HTTP 404: `empty` only when no timezone is known for the symbol (first sight); for a known symbol it is `error` (a Yahoo problem, not a verdict on the entity).
3. HTTP 401 or 403, or any exception whose message contains "Invalid Crumb" or "Unauthorized": `rate_limited` (an auth/crumb failure is provider-wide).
4. An unknown suffix (`symbol_mic` ValueError) is classified inside `fetch` as `empty` with the message, never raised.
5. Settled tail cap (prices): when the requested interval reaches into the last 3 settled sessions and the payload lacks bars for some of them at its end, `settled_through` = the last bar date in the payload, so the missing tail stays a gap and is asked again next run. If the last bar is older than that (suspended, delisted), no cap. Fx: same rule against calendar days.
6. Truncated history: if the first bar is more than 5 sessions after the first session on or after `max(requested_start, metadata firstTradeDate)`, the outcome is `error` ("history truncated").
7. `YF_POLICY` sets `max_consecutive_errors=5`, `max_consecutive_empty=20` (starting values; tune from the attempt log).

Semantics, normalisation (`history.py`; checks run over the padded payload, output trimmed to the requested interval as now; values are never changed by checks):
8. Duplicate bars (two bars with the same local date): keep one row per date (the last with a non-NaN close), carry non-zero dividends and split values from any row of that date, add reason `duplicate_bar`.
9. Single missing sessions: `missing_sessions:<n>` for n ≥ 1 (was ≥ 3). If the TASK-32 small-cap fixtures show single missing sessions are routine on illiquid names, `ask` the coordinator before choosing the threshold.
10. Split-sized jumps (closes are already split-adjusted, so a correct split shows no jump): close/previous close within 3% of 2, 3, 4, 5, 8, 10 or 20, or of their inverses → `unadjusted_split` when that day has a split row, else `split_like_jump`. The existing `jump_x100` rule is unchanged.
11. Dividends too small: 0 < dividend / close < 0.0002 → `dividend_yield_lt_0.02pct` (a pounds-vs-pence mix-up divided by 100).
12. Stale prices: a run of ≥ 5 sessions with an identical close and volume 0 or NaN → each bar in the run gets `stale`.
13. Fx: close/previous close > 1.10 or < 1/1.10 → `fx_jump`; ≥ 5 identical consecutive closes → `stale`.

## Steps
- [ ] Write the failing tests (constructed copies of recorded fixtures, labelled as such in the test):
  - `test_yf_provider.py`:
    - extend `test_exceptions_classified`: prices-missing with tz over a range with sessions → `error`; over a weekend → `ok` empty; 404 with/without known tz; 401, 403, "Invalid Crumb" → `rate_limited`; unknown suffix → `empty`
    - `test_missing_tail_caps_settled_through`
    - `test_old_last_bar_does_not_cap_settled_through`
    - `test_truncated_history_is_error`
    - `test_yf_policy_sets_breakers`
  - `test_yf_history.py`:
    - `test_duplicate_bar_collapsed_and_marked`
    - `test_single_missing_session_marked`
    - `test_split_like_jump_marked`, `test_unadjusted_split_marked`
    - `test_tiny_dividend_marked`
    - `test_stale_run_marked`
    - `test_fx_jump_and_stale_marked`
    - `test_recorded_fixtures_have_no_new_suspects`: every recorded prices/fx fixture gets none of the new reasons (guards against false positives on clean data).
- [ ] Run `uv run pytest packages/alpha_nodes -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(alpha_nodes): harden yfinance prices and fx against transient and silent errors`.

Out of scope: overlap reconciliation with stored facts (TASK-38); dividend-only rows on non-session days; profile.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Prices-missing over a range with sessions, 404 for a known symbol and truncated history are error (never cached); 401/403/Invalid Crumb are rate_limited; unknown suffix is empty
- [ ] #2 settled_through is capped at the last bar when recent sessions are missing at the tail; not capped for old last bars
- [ ] #3 Duplicate bars collapsed; single missing sessions, split-sized jumps, tiny dividends, stale runs and fx jumps/stale marked suspect; normaliser versions bumped to 2
- [ ] #4 Recorded fixtures get none of the new reasons; YF_POLICY sets the breakers; curl_cffi pinned
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
