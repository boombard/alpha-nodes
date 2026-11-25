"""`YFinanceProvider`: prices and fx from Yahoo via yfinance 1.8.0.

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
from alpha_nodes.datasets import FX, PRICES
from alpha_nodes.providers.yfinance.history import (
    FX_NORMALISER_VERSION,
    PRICES_NORMALISER_VERSION,
    YFHistoryPayload,
    normalise_fx,
    normalise_prices,
    payload_from_history,
)

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
)
"""Starting limits; Yahoo publishes none, so tune from the attempt log (finance.md)."""

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
    """Provider for the `prices` and `fx` datasets; fetch is one `Ticker.history` per item.

    Entities are Yahoo symbols for prices (e.g. "BP.L") and currency codes for fx ("GBP").
    Payloads are `YFHistoryPayload`, stored verbatim and normalised by `normalise`.

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
            datasets=frozenset({PRICES.name, FX.name}),
            max_batch=1,
            rate_limit=YF_POLICY,
            pit_reliable={PRICES.name: True, FX.name: True},
        )

    def normaliser_version(self, dataset: str) -> str:
        """Version of the payload -> canonical mapping for `dataset`."""
        return {PRICES.name: PRICES_NORMALISER_VERSION, FX.name: FX_NORMALISER_VERSION}[dataset]

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        """One outcome per item (blocking); yfinance errors are classified, never raised."""
        return [self._fetch_one(dataset.name, item) for item in items]

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        """Map a stored `YFHistoryPayload` (model or its JSON dict) to canonical columns."""
        history = YFHistoryPayload.model_validate(payload)
        if dataset.name == FX.name:
            return normalise_fx(history)
        return normalise_prices(history, symbol_mic(history.symbol))

    def _fetch_one(self, dataset: str, item: WorkItem) -> FetchOutcome:
        interval = item.interval
        if interval is None:
            raise ValueError(f"{dataset} is date-axis; item has no interval")
        is_fx = dataset == FX.name
        symbol = fx_symbol(item.entity) if is_fx else item.entity
        start = min(interval.start, interval.end - self._min_window)
        settled = (
            markets.fx_settled_through(self._clock.now())
            if is_fx
            else markets.settled_through(symbol_mic(symbol), self._clock.now())
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
        except YFRateLimitError as exc:
            return FetchOutcome(item=item, kind="rate_limited", message=str(exc))
        except YFTzMissingError as exc:
            return FetchOutcome(item=item, kind="empty", message=str(exc))
        except YFPricesMissingError as exc:
            if _known_timezone(symbol) is None:
                return FetchOutcome(item=item, kind="empty", message=str(exc))
            # A known symbol with no bars in range is an empty interval, never an empty entity.
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
        except CurlHTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 404:  # Yahoo's answer for a symbol it has never heard of
                return FetchOutcome(item=item, kind="empty", message=str(exc))
            return FetchOutcome(item=item, kind="error", message=f"{type(exc).__name__}: {exc}")
        except _UNREACHABLE as exc:
            return FetchOutcome(item=item, kind="unreachable", message=str(exc))
        except Exception as exc:  # noqa: BLE001 - anything else is a retryable item error
            return FetchOutcome(item=item, kind="error", message=f"{type(exc).__name__}: {exc}")
        return FetchOutcome(
            item=item,
            kind="ok",
            payload=payload,
            settled_through=settled,
            restated_before=_restated_before(payload),
        )


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
