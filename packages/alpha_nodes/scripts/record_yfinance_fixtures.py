"""Live recorder for the yfinance test fixtures (the one sanctioned network use; see TASK-31).

Run once, commit the output, never import from tests:
    uv run python packages/alpha_nodes/scripts/record_yfinance_fixtures.py [--only NAME ...]
Without `--only` only fixtures that do not exist yet are recorded; `--only` re-records exactly
the named ones (file stems, e.g. `profile_BP.L`). Existing TASK-31 price/fx fixtures are
therefore never re-recorded by accident. Payloads are written exactly as
`payload_from_history` / `payload_from_ticker` capture them; never hand-edit.
Prices fixtures get a stats table (missing sessions, zero-volume days, duplicate dates,
non-session bars) printed as markdown for the README.
"""

import argparse
import json
import tempfile
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf
import yfinance.cache as yf_cache
from alpha_nodes.providers.yfinance.fundamentals import payload_from_ticker_statements
from alpha_nodes.providers.yfinance.history import YFHistoryPayload, payload_from_history
from alpha_nodes.providers.yfinance.news import YFNewsPayload
from alpha_nodes.providers.yfinance.profile import payload_from_ticker
from alpha_nodes.providers.yfinance.stats import price_stats

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "yfinance"
CORE_SYMBOLS = ["BP.L", "HSBA.L", "VOD.L", "ASML.AS", "SAP.DE", "NESN.SW", "NOVO-B.CO", "AAPL"]
NEW_CANARIES = ["VUSD.L", "BOOT.L", "ALCLS.PA"]
"""TASK-32 additions: a USD-quoted .L line (Vanguard S&P 500 UCITS ETF), a UK small-cap
(Henry Boot) and a European small-cap (Cellectis, EUR quote, USD reporting)."""
ILLIQUID_SYMBOLS = ["BMT.L"]
"""Prices only, not canaries: an AIM micro-cap with many no-trade days (TASK-37 gap evidence)."""
PRICE_SYMBOLS = CORE_SYMBOLS + NEW_CANARIES + ILLIQUID_SYMBOLS
PROFILE_SYMBOLS = CORE_SYMBOLS + NEW_CANARIES
FUNDAMENTALS_SYMBOLS = [
    "BP.L",
    "HSBA.L",
    "VOD.L",
    "BOOT.L",
    "ASML.AS",
    "SAP.DE",
    "NESN.SW",
    "NOVO-B.CO",
    "AAPL",
]
"""TASK-52: statements and news canaries (no VUSD.L, an ETF; no ALCLS.PA)."""
NEWS_COUNT = 20
FX_SYMBOLS = ["GBPUSD=X", "EURUSD=X", "CHFUSD=X", "DKKUSD=X"]
SPLIT = ("AAPL", date(2020, 8, 28), date(2020, 9, 3))  # 4:1 split effective 2020-08-31
MISSING_PROBES = {  # name -> (symbol, start, end): provoke the two "missing" exceptions
    "probe_http_404": (
        "NOSUCH.XX",
        date(2026, 1, 5),
        date(2026, 1, 9),
    ),  # first sight of an unknown symbol
    "probe_tz_missing": ("NOSUCH.XX", date(2026, 1, 5), date(2026, 1, 9)),  # and the repeat call
    "probe_prices_missing": ("AAPL", date(2026, 1, 3), date(2026, 1, 4)),  # a weekend
}

WANTED = {"probe_tz_missing": "YFTzMissingError"}


def record(symbol: str, start: date, end: date, name: str) -> str | None:
    """Fetch one history window the way the provider does and write it (or the error) as JSON."""
    ticker = yf.Ticker(symbol)
    try:
        frame = ticker.history(
            start=start, end=end + timedelta(days=1), auto_adjust=False, actions=True, repair=True
        )
        doc = payload_from_history(symbol, frame, ticker.history_metadata, start, end).model_dump(
            mode="json"
        )
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        doc = {
            "exception": type(exc).__name__,
            "message": str(exc),
            "symbol": symbol,
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
        }
        print(f"{name}: {type(exc).__name__}: {exc}")
    (OUT / f"{name}.json").write_text(json.dumps(doc, indent=0) + "\n")
    return doc.get("exception")


def record_profile(symbol: str, name: str) -> str | None:
    """Fetch `Ticker.info` and `.isin` and write them as a `YFProfilePayload` (or the error)."""
    ticker = yf.Ticker(symbol)
    try:
        doc = payload_from_ticker(symbol, ticker.info, ticker.isin).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        doc = {"exception": type(exc).__name__, "message": str(exc), "symbol": symbol}
        print(f"{name}: {type(exc).__name__}: {exc}")
    (OUT / f"{name}.json").write_text(json.dumps(doc, indent=0) + "\n")
    return doc.get("exception")


def record_fundamentals(symbol: str, name: str) -> str | None:
    """Fetch the yearly statements and `.info` the way the provider does; write a `YFStatementsPayload`."""
    ticker = yf.Ticker(symbol)
    try:
        doc = payload_from_ticker_statements(
            symbol, ticker.income_stmt, ticker.balance_sheet, ticker.cashflow, ticker.info
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        doc = {"exception": type(exc).__name__, "message": str(exc), "symbol": symbol}
        print(f"{name}: {type(exc).__name__}: {exc}")
    (OUT / f"{name}.json").write_text(json.dumps(doc, indent=0) + "\n")
    return doc.get("exception")


def record_news(symbol: str, name: str) -> str | None:
    """Fetch `Ticker.get_news(count=20)` and write a `YFNewsPayload` (or the error)."""
    ticker = yf.Ticker(symbol)
    try:
        items = json.loads(json.dumps(ticker.get_news(count=NEWS_COUNT), default=str))
        doc = YFNewsPayload(symbol=symbol, items=items).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - recorded verbatim
        doc = {"exception": type(exc).__name__, "message": str(exc), "symbol": symbol}
        print(f"{name}: {type(exc).__name__}: {exc}")
    (OUT / f"{name}.json").write_text(json.dumps(doc, indent=0) + "\n")
    return doc.get("exception")


def print_price_stats() -> None:
    """Print a markdown table of `price_stats` for every recorded prices fixture."""
    print("| Fixture | bars | missing sessions | zero-volume | duplicate dates | non-session |")
    print("|---|---|---|---|---|---|")
    for path in sorted(OUT.glob("prices_*.json")):
        stats = price_stats(YFHistoryPayload.model_validate_json(path.read_text()))
        print(f"| `{path.name}` | " + " | ".join(str(v) for v in stats.values()) + " |")


def targets() -> dict[str, Callable[[], str | None]]:
    """Every price/fx/profile/fundamentals/news fixture by file stem, as a zero-argument recorder."""
    today = date.today()
    out: dict[str, Callable[[], str | None]] = {}
    for sym in PRICE_SYMBOLS:
        out[f"prices_{sym}"] = lambda sym=sym: record(
            sym, today - timedelta(days=730), today - timedelta(days=1), f"prices_{sym}"
        )
    for sym in FX_SYMBOLS:
        out[f"fx_{sym}"] = lambda sym=sym: record(
            sym, today - timedelta(days=365), today - timedelta(days=1), f"fx_{sym}"
        )
    out[f"split_{SPLIT[0]}"] = lambda: record(SPLIT[0], SPLIT[1], SPLIT[2], f"split_{SPLIT[0]}")
    for sym in PROFILE_SYMBOLS:
        out[f"profile_{sym}"] = lambda sym=sym: record_profile(sym, f"profile_{sym}")
    for sym in FUNDAMENTALS_SYMBOLS:
        out[f"fundamentals_{sym}"] = lambda sym=sym: record_fundamentals(sym, f"fundamentals_{sym}")
        out[f"news_{sym}"] = lambda sym=sym: record_news(sym, f"news_{sym}")
    return out


def main() -> None:
    """Record the selected fixtures (default: those missing on disk) and print price stats."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+", metavar="NAME", help="re-record exactly these stems")
    args = parser.parse_args()
    yf.config.debug.hide_exceptions = False
    yf_cache.set_cache_location(
        tempfile.mkdtemp()
    )  # fresh tz cache: unknown symbols behave as on a first run
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = targets()
    if args.only:
        unknown = set(args.only) - set(wanted) - set(MISSING_PROBES)
        if unknown:
            parser.error(f"unknown fixture names: {sorted(unknown)}")
        names = list(args.only)
    else:
        names = [n for n in [*wanted, *MISSING_PROBES] if not (OUT / f"{n}.json").exists()]
    for name in names:
        if name in MISSING_PROBES:
            sym, start, end = MISSING_PROBES[name]
            # An unknown symbol answers HTTP 404 until yfinance has cached its missing timezone
            # (observed: the third call), then YFTzMissingError; repeat until the class shows.
            for _ in range(6):
                if record(sym, start, end, name) == WANTED.get(name, None) or name not in WANTED:
                    break
        else:
            wanted[name]()
    print("yfinance", yf.__version__, "recorded", date.today(), "->", names)
    print_price_stats()


if __name__ == "__main__":
    main()
