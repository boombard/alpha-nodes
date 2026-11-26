"""`EdgarProvider`: US annual fundamentals from SEC XBRL company facts, with filing dates as `known_at`.

The only code that talks to SEC. Entities are Yahoo symbols; the core sees just the declared
capabilities. See documentation/design/finance.md (Providers; Fundamentals), and core.md, Source store.
"""

import json
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd
from curl_cffi import requests as curl_requests
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

from alpha_nodes.datasets import FUNDAMENTALS
from alpha_nodes.providers.edgar.companyfacts import (
    COMPANYFACTS_NORMALISER_VERSION,
    EdgarFactsPayload,
    normalise_companyfacts,
)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
"""SEC's ticker -> CIK map."""
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
"""All XBRL facts one company has filed."""

EDGAR_POLICY = RateLimitPolicy(
    concurrency=2,
    per_second=5,
    burst=2,
    max_rate_limit_episodes=3,
    max_unreachable=5,
    max_error_retries=2,
    max_consecutive_errors=5,
    max_consecutive_empty=None,
)
"""SEC allows 10 requests/s; we use half. The empty breaker is off: a UK/European universe is all
`empty` for EDGAR by design (finance.md, Providers)."""

_TIMEOUT_S = 30
_TICKER_TTL = timedelta(days=7)
_UNREACHABLE = (CurlConnectionError, CurlTimeout, ConnectionError, TimeoutError)
_TICKER_CACHE = "company_tickers.json"


def companyfacts_url(cik: int) -> str:
    """Company-facts URL for a CIK (zero-padded to ten digits as SEC requires)."""
    return COMPANYFACTS_URL.format(cik=cik)


def get_bytes(url: str, user_agent: str) -> bytes:
    """GET `url` with SEC's required descriptive User-Agent; raises curl_cffi `HTTPError` on 4xx/5xx."""
    response = curl_requests.get(
        url, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}, timeout=_TIMEOUT_S
    )
    response.raise_for_status()
    return response.content


class EdgarProvider:
    """Provider for `fundamentals` from SEC company facts; one company-facts request per symbol.

    A symbol with an exchange suffix ("BP.L"), a ticker missing from SEC's map, and a company without
    `us-gaap` annual facts (a 20-F/IFRS filer) are `empty`. HTTP 429 and 403 are `rate_limited`
    (SEC blocks clients it dislikes with 403), connection failures `unreachable`, anything else `error`.

    Args:
        cache_dir: where the ticker map is cached (7 days).
        clock: time source for the cache age; the system clock by default.
        user_agent: descriptive User-Agent with contact details, which SEC requires; never committed.
    """

    name = "edgar"

    def __init__(self, cache_dir: Path, clock: Clock | None = None, *, user_agent: str) -> None:
        if not user_agent.strip():
            raise ValueError("user_agent must not be blank: SEC requires a descriptive User-Agent")
        self._cache_dir = cache_dir
        self._clock = clock or SystemClock()
        self._user_agent = user_agent.strip()
        self.library_version = f"curl_cffi {version('curl_cffi')}"
        self.capabilities = ProviderCapabilities(
            datasets=frozenset({FUNDAMENTALS.name}),
            max_batch=1,
            rate_limit=EDGAR_POLICY,
            pit_reliable={FUNDAMENTALS.name: True},
        )

    def normaliser_version(self, dataset: str) -> str:
        """Version of the payload -> canonical mapping for `dataset`."""
        return {FUNDAMENTALS.name: COMPANYFACTS_NORMALISER_VERSION}[dataset]

    def fetch(self, dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        """One outcome per item (blocking); HTTP and parse errors are classified, never raised."""
        return [self._fetch_one(item) for item in items]

    def normalise(self, dataset: Dataset, raw: RawResponse, payload: Any) -> pd.DataFrame:
        """Map a stored `EdgarFactsPayload` (model or JSON dict) to `fundamentals` rows."""
        return normalise_companyfacts(EdgarFactsPayload.model_validate(payload))

    def _ticker_map(self) -> dict[str, int]:
        """Upper-cased ticker -> CIK, from the cache when younger than 7 days, else from SEC."""
        path = self._cache_dir / _TICKER_CACHE
        now = self._clock.now()
        if path.exists():
            cached = json.loads(path.read_text())
            if now - pd.Timestamp(cached["fetched_at"]).to_pydatetime() < _TICKER_TTL:
                return {k: int(v) for k, v in cached["tickers"].items()}
        doc = json.loads(get_bytes(TICKERS_URL, self._user_agent))
        tickers = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in doc.values()}
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched_at": now.isoformat(), "tickers": tickers}))
        return tickers

    def _fetch_one(self, item: WorkItem) -> FetchOutcome:
        symbol = item.entity.upper()
        if "." in symbol:  # an exchange suffix: not a US listing, nothing to ask SEC
            return FetchOutcome(item=item, kind="empty", message="exchange-suffixed symbol is not a US ticker")
        try:
            cik = self._ticker_map().get(symbol)
            if cik is None:
                return FetchOutcome(item=item, kind="empty", message=f"{symbol} is not in SEC's ticker map")
            payload = EdgarFactsPayload(
                symbol=item.entity,
                cik=cik,
                facts=json.loads(get_bytes(companyfacts_url(cik), self._user_agent)),
            )
        except Exception as exc:  # noqa: BLE001 - classified below
            return _classify(item, exc)
        if normalise_companyfacts(payload).empty:
            return FetchOutcome(item=item, kind="empty", message="no us-gaap annual (10-K) facts")
        return FetchOutcome(item=item, kind="ok", payload=payload)


def _classify(item: WorkItem, exc: Exception) -> FetchOutcome:
    """Map an HTTP, connection or parse failure to a non-ok outcome.

    429 and 403 -> `rate_limited`; 404 on company facts (SEC has none for the CIK) -> `empty`;
    connection failure or timeout -> `unreachable`; anything else, including bad JSON -> retryable `error`.
    """
    if isinstance(exc, CurlHTTPError):
        status = getattr(exc.response, "status_code", None)
        if status in (429, 403):
            return FetchOutcome(item=item, kind="rate_limited", message=str(exc))
        if status == 404:
            return FetchOutcome(item=item, kind="empty", message=str(exc))
        return FetchOutcome(item=item, kind="error", message=f"{type(exc).__name__}: {exc}")
    if isinstance(exc, _UNREACHABLE):
        return FetchOutcome(item=item, kind="unreachable", message=str(exc))
    return FetchOutcome(item=item, kind="error", message=f"{type(exc).__name__}: {exc}")
