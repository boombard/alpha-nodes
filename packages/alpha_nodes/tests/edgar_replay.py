"""A fixture-backed stand-in for SEC's HTTP API, counting the requests it serves.

Test-only. `EdgarReplay.install` swaps it in for `curl_cffi.requests.get` inside the EDGAR
provider, so tests replay the recorded company facts offline (see fixtures/edgar/README.md).
"""

import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha_nodes.providers.edgar import provider as provider_mod
from alpha_nodes.providers.edgar.companyfacts import EdgarFactsPayload
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from pydantic import BaseModel

EDGAR_FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def load_payload(symbol: str) -> EdgarFactsPayload:
    """The recorded company facts of `symbol` (AAPL, KO or LAKE) as the provider stores them."""
    tickers = json.loads(gzip.decompress((EDGAR_FIXTURES / "company_tickers.json.gz").read_bytes()))
    cik = next(int(v["cik_str"]) for v in tickers.values() if v["ticker"] == symbol)
    facts = json.loads(gzip.decompress((EDGAR_FIXTURES / f"companyfacts_{symbol}.json.gz").read_bytes()))
    return EdgarFactsPayload(symbol=symbol, cik=cik, facts=facts)


class ReplayRequest(BaseModel):
    """One request the replay served."""

    url: str
    user_agent: str | None


class _Response:
    def __init__(self, status: int, content: bytes) -> None:
        self.status_code, self.content = status, content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = CurlHTTPError(f"HTTP Error {self.status_code}: ")
            error.response = SimpleNamespace(status_code=self.status_code)  # type: ignore[assignment]
            raise error


class EdgarReplay:
    """Serves the recorded ticker map and company facts; anything else answers HTTP 404.

    Attributes:
        requests: every request in order; empty means the network was never needed.
        fail_with: when set, an exception raised for every request, or an int HTTP status
            answered for every request.
    """

    def __init__(self) -> None:
        self.requests: list[ReplayRequest] = []
        self.fail_with: Exception | int | None = None
        self.tickers_doc: dict[str, Any] = json.loads(
            gzip.decompress((EDGAR_FIXTURES / "company_tickers.json.gz").read_bytes())
        )

    def _body(self, url: str) -> bytes | None:
        if url == provider_mod.TICKERS_URL:
            return json.dumps(self.tickers_doc).encode()
        for entry in self.tickers_doc.values():
            if url == provider_mod.companyfacts_url(int(entry["cik_str"])):
                path = EDGAR_FIXTURES / f"companyfacts_{entry['ticker']}.json.gz"
                return gzip.decompress(path.read_bytes()) if path.exists() else None
        return None

    def __call__(self, url: str, *, headers: dict[str, str] | None = None, **_: Any) -> _Response:
        self.requests.append(ReplayRequest(url=url, user_agent=(headers or {}).get("User-Agent")))
        if isinstance(self.fail_with, Exception):
            raise self.fail_with
        if isinstance(self.fail_with, int):
            return _Response(self.fail_with, b"")
        body = self._body(url)
        return _Response(404, b"") if body is None else _Response(200, body)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace `curl_cffi.requests.get` in the provider module; no network."""
        monkeypatch.setattr(provider_mod.curl_requests, "get", self)
