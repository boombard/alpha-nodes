"""A fixture-backed stand-in for `yfinance.Ticker`, counting the calls it serves.

Test-only. `YFReplay.install` swaps it in for `yfinance.Ticker` inside the yfinance provider, so a
whole run can be replayed offline from the recorded fixtures (see fixtures/yfinance/README.md).
"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import yfinance.cache as yf_cache
from alpha_nodes.providers.yfinance import provider as provider_mod
from alpha_nodes.providers.yfinance.fundamentals import YFStatementsPayload
from alpha_nodes.providers.yfinance.history import YFHistoryPayload
from alpha_nodes.providers.yfinance.news import YFNewsPayload
from alpha_nodes.providers.yfinance.profile import YFProfilePayload
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from pydantic import BaseModel

from .conftest import YF_FIXTURES, yf_frame

FX_DERIVED_FROM = "EURUSD=X"
"""No SEK/NOK/PLN fx fixtures were recorded; those currencies replay the EUR payload, relabelled."""


class ReplayCall(BaseModel):
    """One yfinance access served by the replay."""

    symbol: str
    kind: str  # "history", "info", "statements" or "news"


class YFReplay:
    """Serves recorded payloads as `yfinance.Ticker`; unknown symbols answer HTTP 404.

    Args:
        fixtures: directory of `prices_*`, `fx_*`, `profile_*`, `fundamentals_*` and `news_*` payload files.

    Attributes:
        calls: every history/info access, in order; empty means the network was never needed.
    """

    def __init__(self, fixtures: Path = YF_FIXTURES) -> None:
        self.fixtures = fixtures
        self.calls: list[ReplayCall] = []
        self.histories: dict[str, YFHistoryPayload] = {}
        self.profiles: dict[str, YFProfilePayload] = {}
        self.statements: dict[str, YFStatementsPayload] = {}
        self.news: dict[str, YFNewsPayload] = {}

    def _statements(self, symbol: str) -> YFStatementsPayload | None:
        if symbol not in self.statements:
            path = self.fixtures / f"fundamentals_{symbol}.json"
            if not path.exists():
                return None
            self.statements[symbol] = YFStatementsPayload.model_validate_json(path.read_text())
        return self.statements[symbol]

    def _news(self, symbol: str) -> YFNewsPayload | None:
        if symbol not in self.news:
            path = self.fixtures / f"news_{symbol}.json"
            if not path.exists():
                return None
            self.news[symbol] = YFNewsPayload.model_validate_json(path.read_text())
        return self.news[symbol]

    def _history(self, symbol: str) -> YFHistoryPayload | None:
        if symbol not in self.histories:
            is_fx = symbol.endswith("USD=X")
            stem = f"fx_{symbol}" if is_fx else f"prices_{symbol}"
            path = self.fixtures / f"{stem}.json"
            if not path.exists() and is_fx:
                path = self.fixtures / f"fx_{FX_DERIVED_FROM}.json"
            if not path.exists():
                return None
            payload = YFHistoryPayload.model_validate_json(path.read_text())
            self.histories[symbol] = payload.model_copy(update={"symbol": symbol})
        return self.histories[symbol]

    def _profile(self, symbol: str) -> YFProfilePayload | None:
        if symbol not in self.profiles:
            path = self.fixtures / f"profile_{symbol}.json"
            if not path.exists():
                return None
            self.profiles[symbol] = YFProfilePayload.model_validate_json(path.read_text())
        return self.profiles[symbol]

    def add_bar(self, symbol: str, day: date, close: float) -> None:
        """Append a bar for `day` (a copy of the last bar with `close`), as a live session bar."""
        payload = self._history(symbol)
        assert payload is not None
        row = list(payload.data[-1])
        row[payload.columns.index("Close")] = close
        payload.index.append(f"{day.isoformat()}T00:00:00+00:00")
        payload.data.append(row)

    def scale_close(self, symbol: str, day: date, factor: float) -> None:
        """Multiply the close of `day`'s bar by `factor`; constructs a bad-tick variant of a fixture."""
        payload = self._history(symbol)
        assert payload is not None
        pos = next(i for i, ts in enumerate(payload.index) if ts.startswith(day.isoformat()))
        col = payload.columns.index("Close")
        payload.data[pos][col] = float(payload.data[pos][col] or 0) * factor

    def __call__(self, symbol: str) -> "_ReplayTicker":
        return _ReplayTicker(self, symbol)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace `yfinance.Ticker` and the tz cache lookup in the provider; no network, no disk cache."""
        monkeypatch.setattr(provider_mod.yf, "Ticker", self)
        monkeypatch.setattr(yf_cache, "set_cache_location", lambda _dir: None)
        monkeypatch.setattr(provider_mod, "_known_timezone", lambda _symbol: None)


def _not_found() -> CurlHTTPError:
    """What curl_cffi raises for Yahoo's first-sight answer to an unknown symbol (probe_http_404.json)."""
    error = CurlHTTPError("HTTP Error 404: ")
    error.response = SimpleNamespace(status_code=404)  # type: ignore[assignment]
    return error


class _ReplayTicker:
    def __init__(self, replay: YFReplay, symbol: str) -> None:
        self.replay, self.symbol = replay, symbol

    def history(self, *, start: date, end: date, **_: Any) -> pd.DataFrame:
        self.replay.calls.append(ReplayCall(symbol=self.symbol, kind="history"))
        payload = self.replay._history(self.symbol)
        if payload is None:
            raise _not_found()
        frame = yf_frame(payload)
        days = pd.Index([ts.date() for ts in frame.index])
        return pd.DataFrame(frame[(days >= start) & (days < end)])

    @property
    def history_metadata(self) -> dict[str, Any]:
        payload = self.replay._history(self.symbol)
        assert payload is not None
        return payload.metadata

    @property
    def info(self) -> dict[str, Any]:
        self.replay.calls.append(ReplayCall(symbol=self.symbol, kind="info"))
        profile = self.replay._profile(self.symbol)
        if profile is None:
            raise _not_found()
        statements = self.replay._statements(self.symbol)
        if statements is None:
            return profile.info
        return {  # the two facts the fundamentals fetch reads agree with the statements fixture
            **profile.info,
            "financialCurrency": statements.financial_currency,
            "netIncomeToCommon": statements.info_net_income,
        }

    def _statement(self, attribute: str) -> pd.DataFrame:
        """A recorded statement as the frame yfinance returns (line items x period ends)."""
        self.replay.calls.append(ReplayCall(symbol=self.symbol, kind="statements"))
        statements = self.replay._statements(self.symbol)
        if statements is None:
            return pd.DataFrame()
        dump = getattr(statements, attribute)
        return pd.DataFrame(
            dump["data"], index=dump["index"], columns=pd.to_datetime(dump["columns"]), dtype=float
        )

    @property
    def income_stmt(self) -> pd.DataFrame:
        return self._statement("income")

    @property
    def balance_sheet(self) -> pd.DataFrame:
        return self._statement("balance")

    @property
    def cashflow(self) -> pd.DataFrame:
        return self._statement("cashflow")

    def get_news(self, count: int = 10, **_: Any) -> list[dict[str, Any]]:
        self.replay.calls.append(ReplayCall(symbol=self.symbol, kind="news"))
        news = self.replay._news(self.symbol)
        return [] if news is None else news.items[:count]

    @property
    def isin(self) -> str:
        profile = self.replay._profile(self.symbol)
        assert profile is not None
        return profile.isin or "-"
