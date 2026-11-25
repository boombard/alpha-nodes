"""Live canary: does Yahoo (via yfinance) still look like the recorded fixtures?

Not part of the test suite and the only live code besides the recorder (finance.md, Data
quality principle 5). Usage:
    uv run python packages/alpha_nodes/scripts/canary.py [--symbols BP.L AAPL ...] [--concurrency 4]

Steps: a health check (AAPL over 5 days), then each canary symbol fetched live through
`YFinanceProvider` (no store) for prices and profile, normalised and compared with the
fixtures; then the same fetches through a thread pool (the scheduler's shape) twice, cold
(fresh tz/cookie caches, so first sights race) and warm, to surface cache-lock and crumb errors; then a `repair=True` vs `repair=False` request count.
HTTP requests are counted by wrapping `curl_cffi.requests.Session.request`, the single
method the shared yfinance session routes every `get`/`post` through.

Exit codes: 0 no drift, 1 drift (or a failed fetch), 2 Yahoo unhealthy.
"""

import argparse
import sys
import tempfile
import threading
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from alpha_nodes.datasets import PRICES, PROFILE
from alpha_nodes.providers.yfinance.history import YFHistoryPayload, normalise_prices
from alpha_nodes.providers.yfinance.profile import YFProfilePayload, normalise_profile
from alpha_nodes.providers.yfinance.provider import YFinanceProvider, symbol_mic
from curl_cffi.requests import Session
from lensgraph.sources import DateInterval, FetchOutcome, WorkItem

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "yfinance"
SYMBOLS = [
    "BP.L",
    "HSBA.L",
    "VOD.L",
    "ASML.AS",
    "SAP.DE",
    "NESN.SW",
    "NOVO-B.CO",
    "AAPL",
    "VUSD.L",
    "BOOT.L",
    "ALCLS.PA",
]
CLOSE_RATIO = (0.5, 2.0)
"""Live close / fixture close outside this range at the last overlapping date is drift."""
WINDOW_DAYS = 30
EXIT_OK, EXIT_DRIFT, EXIT_UNHEALTHY = 0, 1, 2


def compare_prices(fixture: pd.DataFrame, live: pd.DataFrame) -> list[str]:
    """Drift messages between a fixture's normalised prices and a live frame; [] when equal.

    Checks column names and dtypes, currency, whether the `minor_unit` repair applies, and
    that the live close at the last date both frames hold is within 0.5x-2x of the fixture's
    (a x100 unit change fails this). Pure; the script's network part is not unit-tested.
    """
    problems: list[str] = []
    if list(fixture.columns) != list(live.columns):
        problems.append(f"columns {list(live.columns)} != {list(fixture.columns)}")
    else:
        for col in fixture.columns:
            if str(fixture[col].dtype) != str(live[col].dtype):
                problems.append(f"dtype of {col}: {live[col].dtype} != {fixture[col].dtype}")
    if problems:
        return problems
    if set(fixture["currency"]) != set(live["currency"]):
        problems.append(f"currency {set(live['currency'])} != {set(fixture['currency'])}")
    if _minor_unit(fixture) != _minor_unit(live):
        problems.append(f"repairs: minor_unit {_minor_unit(fixture)} -> {_minor_unit(live)}")
    shared = sorted(set(fixture["date"]) & set(live["date"]))
    if not shared:
        problems.append("no overlapping dates between fixture and live data")
        return problems
    old = float(fixture.loc[fixture["date"] == shared[-1], "close"].iloc[0])
    new = float(live.loc[live["date"] == shared[-1], "close"].iloc[0])
    if not CLOSE_RATIO[0] <= new / old <= CLOSE_RATIO[1]:
        problems.append(f"close on {shared[-1].date()}: live {new:g} vs fixture {old:g}")
    return problems


def _minor_unit(frame: pd.DataFrame) -> bool:
    """True when every row carries the `minor_unit` repair (a pence-quoted listing)."""
    return bool(len(frame)) and all("minor_unit" in r for r in frame["repairs"])


def compare_profile(fixture: pd.DataFrame, live: pd.DataFrame) -> list[str]:
    """Drift messages between fixture and live normalised profiles: columns and currencies."""
    if list(fixture.columns) != list(live.columns):
        return [f"columns {list(live.columns)} != {list(fixture.columns)}"]
    return [
        f"{col}: {live[col].iloc[0]!r} != {fixture[col].iloc[0]!r}"
        for col in ("trading_currency", "reporting_currency")
        if fixture[col].iloc[0] != live[col].iloc[0]
    ]


class RequestCounter:
    """Counts HTTP requests per labelled call by wrapping `curl_cffi.requests.Session.request`.

    The label is thread-local, so concurrent calls are counted separately.
    """

    def __init__(self) -> None:
        self._local = threading.local()
        self._lock = threading.Lock()
        self.counts: Counter[str] = Counter()

    def install(self) -> None:
        """Patch `Session.request` process-wide so labelled calls are counted; call once."""
        original = Session.request
        counter = self

        def counted(session: Any, *args: Any, **kwargs: Any) -> Any:
            label = getattr(counter._local, "label", None)
            if label is not None:
                with counter._lock:
                    counter.counts[label] += 1
            return original(session, *args, **kwargs)

        Session.request = counted  # type: ignore[method-assign,assignment]

    @contextmanager
    def label(self, name: str) -> Iterator[None]:
        """Attribute every request made by this thread inside the block to `name`."""
        self._local.label = name
        try:
            yield
        finally:
            self._local.label = None


def _fixture_prices(symbol: str) -> tuple[YFHistoryPayload, pd.DataFrame]:
    payload = YFHistoryPayload.model_validate_json((FIXTURES / f"prices_{symbol}.json").read_text())
    return payload, normalise_prices(payload, symbol_mic(symbol))


def _fixture_profile(symbol: str) -> pd.DataFrame:
    payload = YFProfilePayload.model_validate_json(
        (FIXTURES / f"profile_{symbol}.json").read_text()
    )
    return normalise_profile(payload, symbol_mic(symbol))


def _fetch(
    provider: YFinanceProvider, counter: RequestCounter, label: str, dataset: str, item: WorkItem
) -> tuple[FetchOutcome, int]:
    """One provider fetch; returns the outcome and the HTTP requests it made."""
    before = counter.counts[label]
    with counter.label(label):
        (outcome,) = provider.fetch(PRICES if dataset == "prices" else PROFILE, [item])
    return outcome, counter.counts[label] - before


def _items(symbol: str) -> tuple[WorkItem, WorkItem]:
    """Live work items for a canary: prices over the fixture's last 30 days, and its profile."""
    end = YFHistoryPayload.model_validate_json(
        (FIXTURES / f"prices_{symbol}.json").read_text()
    ).requested_end
    interval = DateInterval(start=end - timedelta(days=WINDOW_DAYS), end=end)
    return (
        WorkItem(dataset="prices", entity=symbol, interval=interval),
        WorkItem(dataset="profile", entity=symbol, interval=None),
    )


def check_health() -> str | None:
    """None when Yahoo answers a 5-day AAPL history; else the reason (a 404, empty or error)."""
    try:
        frame = yf.Ticker("AAPL").history(period="5d")
    except Exception as exc:  # noqa: BLE001 - any failure means unhealthy
        return f"{type(exc).__name__}: {exc}"
    return "empty answer" if frame.empty else None


def check_symbol(
    provider: YFinanceProvider, counter: RequestCounter, symbol: str, tag: str
) -> tuple[list[str], dict[str, int]]:
    """Fetch prices and profile live, compare with fixtures; (problems, requests per dataset)."""
    problems: list[str] = []
    requests: dict[str, int] = {}
    prices_item, profile_item = _items(symbol)
    for dataset, item in (("prices", prices_item), ("profile", profile_item)):
        outcome, requests[dataset] = _fetch(
            provider, counter, f"{tag}:{dataset}:{symbol}", dataset, item
        )
        if outcome.kind != "ok":
            problems.append(f"{dataset} fetch {outcome.kind}: {outcome.message}")
            continue
        if dataset == "prices":
            live = normalise_prices(
                YFHistoryPayload.model_validate(outcome.payload), symbol_mic(symbol)
            )
            problems += [f"prices {p}" for p in compare_prices(_fixture_prices(symbol)[1], live)]
        else:
            live = normalise_profile(
                YFProfilePayload.model_validate(outcome.payload), symbol_mic(symbol)
            )
            problems += [f"profile {p}" for p in compare_profile(_fixture_profile(symbol), live)]
    return problems, requests


def concurrent_pass(
    provider: YFinanceProvider, counter: RequestCounter, symbols: list[str], workers: int, tag: str
) -> bool:
    """Run `check_symbol` for every symbol through a thread pool; True if anything drifted.

    Exceptions (e.g. SQLite "database is locked", crumb errors) are printed and count as drift.
    """
    print(f"concurrent pass '{tag}', {workers} workers:")
    drifted = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {s: pool.submit(check_symbol, provider, counter, s, tag) for s in symbols}
    for symbol, future in futures.items():
        try:
            problems, requests = future.result()
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            print(f"{symbol:10} CONCURRENCY ERROR {type(exc).__name__}: {exc}")
            drifted = True
            continue
        drifted |= bool(problems)
        status = "DRIFT " + "; ".join(problems) if problems else "ok"
        print(f"{symbol:10} {status}  [{tag} requests: {requests}]")
    return drifted


def repair_request_counts(counter: RequestCounter, symbol: str) -> tuple[int, int]:
    """(requests with repair=True, with repair=False) for one `history()` call, caches warm.

    The windows differ by a day per call: yfinance answers a repeated identical request from
    its own cache (observed: 0 requests), which would hide the real count.
    """
    end = date.today() - timedelta(days=1)
    counts: dict[bool, int] = {}
    for repair, back in ((False, 183), (True, 184)):
        label = f"repair={repair}:{symbol}"
        with counter.label(label):
            yf.Ticker(symbol).history(
                start=end - timedelta(days=back),
                end=end + timedelta(days=1),
                auto_adjust=False,
                actions=True,
                repair=repair,
            )
        counts[repair] = counter.counts[label]
    return counts[True], counts[False]


def main(argv: list[str] | None = None) -> int:
    """Run the canary; returns the exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args(argv)

    counter = RequestCounter()
    counter.install()
    provider = YFinanceProvider(Path(tempfile.mkdtemp()))  # fresh caches: first sight is real

    unhealthy = check_health()
    if unhealthy:
        print(f"yahoo unhealthy: {unhealthy}")
        return EXIT_UNHEALTHY
    print("yahoo healthy: AAPL 5d history ok")

    drifted = False
    for symbol in args.symbols:
        problems, requests = check_symbol(provider, counter, symbol, "first")
        drifted |= bool(problems)
        status = "DRIFT " + "; ".join(problems) if problems else "ok"
        print(f"{symbol:10} {status}  [first-sight requests: {requests}]")

    # Cold: a fresh provider moves yfinance's tz/cookie caches to a new empty directory, so
    # every first sight writes them concurrently (the "database is locked" risk). Warm: again.
    cold_provider = YFinanceProvider(Path(tempfile.mkdtemp()))
    for tag in ("cold", "warm"):
        drifted |= concurrent_pass(cold_provider, counter, args.symbols, args.concurrency, tag)

    for symbol in args.symbols[:2]:
        with_repair, without = repair_request_counts(counter, symbol)
        print(f"{symbol:10} history requests: repair=True {with_repair}, repair=False {without}")

    print("exit", EXIT_DRIFT if drifted else EXIT_OK)
    return EXIT_DRIFT if drifted else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
