"""`YFinanceProvider`: prices, fx and profile from Yahoo via yfinance 1.8.0.

The only code that knows yfinance names, Yahoo symbols and Yahoo quirks. The core sees
just the declared capabilities. See documentation/design/finance.md, "yfinance fetching
and throttling", and core.md, Source store.
"""

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
import yfinance._http as yf_http
import yfinance.cache as yf_cache
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from curl_cffi.requests.exceptions import Timeout as CurlTimeout
from lensgraph.sources import (
    Clock,
    Dataset,
    FetchOutcome,
    ProviderCapabilities,
    RateLimitPolicy,
    RawResponse,
    SystemClock,
    WorkItem,
)
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError, YFTzMissingError

from alpha_nodes import markets
from alpha_nodes.datasets import FX, PRICES, PROFILE
from alpha_nodes.providers.yfinance.history import (
    FX_NORMALISER_VERSION,
    PRICES_NORMALISER_VERSION,
    YFHistoryPayload,
    normalise_fx,
    normalise_prices,
    payload_from_history,
)
from alpha_nodes.providers.yfinance.profile import (
    PROFILE_NORMALISER_VERSION,
    YFProfilePayload,
    normalise_profile,
    payload_from_ticker,
)
from alpha_nodes.units import to_major

SUFFIX_MIC: dict[str, str] = {
    ".L": "XLON",
    ".PA": "XPAR",
    ".AS": "XAMS",
    ".BR": "XBRU",
    ".LS": "XLIS",
    ".IR": "XDUB",
    ".DE": "XETR",
    ".MI": "XMIL",
    ".MC": "XMAD",
    ".SW": "XSWX",
    ".ST": "XSTO",
    ".CO": "XCSE",
    ".OL": "XOSL",
    ".HE": "XHEL",
}
"""Yahoo ticker suffix -> MIC; a symbol without a suffix is a US listing."""
US_MIC = "XNYS"

YF_POLICY = RateLimitPolicy(
    concurrency=4,
    per_second=2,
    burst=4,
    backoff_s=(30, 60, 120, 240),
    jitter=0.25,
    max_rate_limit_episodes=3,
    max_unreachable=5,
    max_error_retries=2,
    max_consecutive_errors=5,
    max_consecutive_empty=20,
)
"""Starting limits; Yahoo publishes none, so tune from the attempt log (finance.md).

The consecutive error/empty limits are the core breakers (core.md, Source store): a run of
distinct entities all failing or all empty means Yahoo is broken, not that every entity is.
"""

_SETTLED_TAIL_SESSIONS = 3
"""Last settled sessions in which a missing bar is treated as Yahoo lag, not a verdict."""
_TRUNCATION_SESSIONS = 5
"""First bar later than this many sessions after the expected start means truncated history."""

_SPLIT_RESTATEMENT_WINDOW = timedelta(days=730)
_TIMEOUT_S = 15
_RETRIES = 2
_UNREACHABLE = (CurlConnectionError, CurlTimeout, ConnectionError, TimeoutError)


def symbol_mic(symbol: str) -> str:
    """MIC of the listing a Yahoo symbol refers to; ValueError naming an unknown suffix."""
    head, dot, suffix = symbol.rpartition(".")
    if not dot or not head:
        return US_MIC
    try:
        return SUFFIX_MIC[f".{suffix}"]
    except KeyError:
        raise ValueError(f"unknown Yahoo exchange suffix .{suffix} in {symbol!r}") from None


def fx_symbol(currency: str) -> str:
    """Yahoo symbol for a currency's USD rate, e.g. "GBP" -> "GBPUSD=X"."""
    return f"{currency}USD=X"


def _known_timezone(symbol: str) -> str | None:
    """Exchange timezone yfinance has cached for `symbol`, None if it never resolved one."""
    cache = yf_cache.get_tz_cache()
    return cache.lookup(symbol) if cache is not None else None


class YFinanceProvider:
    """Provider for `prices`, `fx` and `profile`; fetch is one yfinance call group per item.

    Entities are Yahoo symbols for prices and profile (e.g. "BP.L") and currency codes for
    fx ("GBP"). Prices and fx fetch one `Ticker.history` and store a `YFHistoryPayload`;
    profile reads `Ticker.info` and `.isin` (about 3 requests, finance.md "Profile cost") and
    stores a `YFProfilePayload`. Payloads are stored verbatim and normalised by `normalise`.

    Args:
        cache_dir: where yfinance keeps its timezone, cookie and ISIN caches.
        clock: time source for the settled cut-off; the system clock by default.
        min_window_days: every request reaches back at least this far before the interval
            end, so yfinance's repair and our checks have context for short top-ups.
    """

    name = "yfinance"

    def __init__(
        self, cache_dir: Path, clock: Clock | None = None, *, min_window_days: int = 183
    ) -> None:
        if not yf_http.HAS_CURL_CFFI:
            raise RuntimeError(
                "curl_cffi is required: without it yfinance falls back to plain requests, "
                "which Yahoo may block"
            )
        yf_cache.set_cache_location(str(cache_dir))
        yf.config.debug.hide_exceptions = False
        yf.config.network.retries = _RETRIES
        self._clock = clock or SystemClock()
        self._min_window = timedelta(days=min_window_days)
        self.library_version = yf.__version__
        self.capabilities = ProviderCapabilities(
            datasets=frozenset({PRICES.name, FX.name, PROFILE.name}),
            max_batch=1,
            rate_limit=YF_POLICY,
            pit_reliable={PRICES.name: True, FX.name: True, PROFILE.name: False},
        )

    def normaliser_version(self, dataset: str) -> str:
        """Version of the payload -> canonical mapping for `dataset`."""
        return {
            PRICES.name: PRICES_NORMALISER_VERSION,
            FX.name: FX_NORMALISER_VERSION,
            PROFILE.name: PROFILE_NORMALISER_VERSION,
        }[dataset]

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        """One outcome per item (blocking); yfinance errors are classified, never raised."""
        return [self._fetch_one(dataset.name, item) for item in items]

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        """Map a stored payload (`YFHistoryPayload` or `YFProfilePayload`, model or JSON dict)."""
        if dataset.name == PROFILE.name:
            profile = YFProfilePayload.model_validate(payload)
            return normalise_profile(profile, symbol_mic(profile.symbol))
        history = YFHistoryPayload.model_validate(payload)
        if dataset.name == FX.name:
            return normalise_fx(history)
        return normalise_prices(history, symbol_mic(history.symbol))

    def _fetch_profile(self, item: WorkItem) -> FetchOutcome:
        """`Ticker.info` plus `.isin` for one symbol.

        Empty info, or a stub without a currency (Yahoo's answer for unknown symbols), is
        `empty`; a currency code `to_major` rejects is a retryable `error`. Both are caught
        here so `normalise_profile` never sees them (its ValueError is only a backstop).
        """
        symbol = item.entity
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            if not info:
                return FetchOutcome(item=item, kind="empty", message="empty info")
            currency = info.get("currency")
            if currency is None:  # Yahoo's stub answer for an unknown or delisted symbol
                return FetchOutcome(
                    item=item, kind="empty", message="no currency in info: unknown symbol"
                )
            to_major(str(currency))  # ValueError for an unrecognised code, classified below
            isin = ticker.isin
            payload = payload_from_ticker(symbol, dict(info), isin)
        except Exception as exc:  # noqa: BLE001 - classified below
            return _classify(item, exc, known_tz=_known_timezone(symbol) is not None)
        return FetchOutcome(item=item, kind="ok", payload=payload)

    def _fetch_one(self, dataset: str, item: WorkItem) -> FetchOutcome:
        if dataset == PROFILE.name:
            return self._fetch_profile(item)
        interval = item.interval
        if interval is None:
            raise ValueError(f"{dataset} is date-axis; item has no interval")
        is_fx = dataset == FX.name
        symbol = fx_symbol(item.entity) if is_fx else item.entity
        start = min(interval.start, interval.end - self._min_window)
        now = self._clock.now()
        try:
            mic = None if is_fx else symbol_mic(symbol)
        except ValueError as exc:  # unknown suffix: nothing to fetch, a verdict on the symbol
            return FetchOutcome(item=item, kind="empty", message=str(exc))
        settled = (
            markets.fx_settled_through(now) if mic is None else markets.settled_through(mic, now)
        )
        try:
            ticker = yf.Ticker(symbol)
            frame = ticker.history(
                start=start,
                end=interval.end + timedelta(days=1),
                auto_adjust=False,
                actions=True,
                repair=True,
                timeout=_TIMEOUT_S,
            )
            payload = payload_from_history(
                symbol, frame, ticker.history_metadata, interval.start, interval.end
            )
        except YFPricesMissingError as exc:
            if _known_timezone(symbol) is None:
                return FetchOutcome(item=item, kind="empty", message=str(exc))
            n = _session_count(mic, interval.start, interval.end)
            if n:  # the store never refetches covered ranges, so a glitch must not be cached
                return FetchOutcome(
                    item=item, kind="error", message=f"no bars for a range with {n} sessions: {exc}"
                )
            payload = YFHistoryPayload(
                symbol=symbol,
                metadata={},
                columns=[],
                index=[],
                data=[],
                requested_start=interval.start,
                requested_end=interval.end,
            )
            return FetchOutcome(
                item=item, kind="ok", payload=payload, settled_through=settled, message=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 - classified below
            return _classify(item, exc, known_tz=_known_timezone(symbol) is not None)
        if mic is not None and _is_truncated(payload, mic, start):
            return FetchOutcome(
                item=item,
                kind="error",
                message=f"history truncated: first bar {payload.index[0][:10]}",
            )
        settled = _cap_settled(payload, mic, settled)
        return FetchOutcome(
            item=item,
            kind="ok",
            payload=payload,
            settled_through=settled,
            restated_before=_restated_before(payload),
        )


_AUTH_MARKERS = ("Invalid Crumb", "Unauthorized")


def _classify(item: WorkItem, exc: Exception, *, known_tz: bool) -> FetchOutcome:
    """Map a yfinance/curl_cffi exception to a non-ok outcome; shared by every dataset.

    Rate limit, HTTP 401/403 and crumb/unauthorized failures -> `rate_limited` (an auth
    failure is provider-wide); unknown symbol (missing timezone) -> `empty`; HTTP 404 ->
    `empty` on first sight (`known_tz` False) but `error` for a symbol Yahoo has served
    before (a Yahoo problem, not a verdict); connection failure or timeout ->
    `unreachable`; anything else -> retryable `error`.
    """
    if isinstance(exc, YFRateLimitError) or any(m in str(exc) for m in _AUTH_MARKERS):
        return FetchOutcome(item=item, kind="rate_limited", message=str(exc))
    if isinstance(exc, YFTzMissingError):
        return FetchOutcome(item=item, kind="empty", message=str(exc))
    if isinstance(exc, CurlHTTPError):
        status = getattr(exc.response, "status_code", None)
        if status in (401, 403):
            return FetchOutcome(item=item, kind="rate_limited", message=str(exc))
        if status == 404 and not known_tz:  # Yahoo: never heard of it
            return FetchOutcome(item=item, kind="empty", message=str(exc))
        return FetchOutcome(item=item, kind="error", message=f"{type(exc).__name__}: {exc}")
    if isinstance(exc, _UNREACHABLE):
        return FetchOutcome(item=item, kind="unreachable", message=str(exc))
    return FetchOutcome(item=item, kind="error", message=f"{type(exc).__name__}: {exc}")


def _session_count(mic: str | None, start: date, end: date) -> int:
    """Trading days in [start, end]: exchange sessions, or every calendar day for fx (`mic` None)."""
    if mic is None:
        return (end - start).days + 1
    return len(markets.sessions(mic, start, end))


def _bar_days(payload: YFHistoryPayload) -> list[date]:
    return [date.fromisoformat(ts[:10]) for ts in payload.index]


def _is_truncated(payload: YFHistoryPayload, mic: str, start: date) -> bool:
    """True if the first bar is over `_TRUNCATION_SESSIONS` sessions after the expected start.

    Expected start is the later of the request start and the listing's `firstTradeDate`
    (from the chart metadata), moved to the first session on or after it. Yahoo sometimes
    answers a long request with only its recent part, which the store would keep forever.
    """
    days = _bar_days(payload)
    if not days:
        return False
    expected = start
    first_trade = payload.metadata.get("firstTradeDate")
    if isinstance(first_trade, str):
        try:
            expected = max(expected, date.fromisoformat(first_trade[:10]))
        except ValueError:
            pass
    horizon = markets.sessions(mic, expected, days[0])
    return len(horizon) - 1 > _TRUNCATION_SESSIONS if horizon else False


def _cap_settled(payload: YFHistoryPayload, mic: str | None, settled: date | None) -> date | None:
    """Cap `settled_through` at the last bar when the newest settled sessions lack bars.

    Yahoo lags on small caps and fx; a missing tail stays a gap and is asked again next run
    (finance.md, Settled tail). A last bar older than the last `_SETTLED_TAIL_SESSIONS`
    settled sessions (suspended, delisted) does not cap. Fx counts calendar days.
    """
    if settled is None or not payload.index:
        return settled
    if mic is None:
        tail = [settled - timedelta(days=i) for i in range(_SETTLED_TAIL_SESSIONS - 1, -1, -1)]
    else:
        tail = markets.sessions(mic, settled - timedelta(days=14), settled)[
            -_SETTLED_TAIL_SESSIONS:
        ]
    if not tail:
        return settled
    last_bar = max((d for d in _bar_days(payload) if d <= settled), default=None)
    if last_bar is not None and tail[0] <= last_bar < settled:
        return last_bar
    return settled


def _restated_before(payload: YFHistoryPayload) -> date | None:
    """Latest split inside the requested interval that makes earlier stored closes stale.

    Only requests that start within two years before the split count: a top-up or recent
    window may sit on closes adjusted differently now (finance.md, Prices and point-in-time).
    """
    if "Stock Splits" not in payload.columns:
        return None
    pos = payload.columns.index("Stock Splits")
    split_days = [
        date.fromisoformat(ts[:10])
        for ts, row in zip(payload.index, payload.data, strict=True)
        if row[pos]
    ]
    inside = [
        d
        for d in split_days
        if payload.requested_start <= d <= payload.requested_end
        and payload.requested_start > d - _SPLIT_RESTATEMENT_WINDOW
    ]
    return max(inside, default=None)
