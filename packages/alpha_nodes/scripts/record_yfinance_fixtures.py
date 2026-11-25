"""Live recorder for the yfinance test fixtures (the one sanctioned network use; see TASK-31).

Run once, commit the output, never import from tests:
    uv run python packages/alpha_nodes/scripts/record_yfinance_fixtures.py
Payloads are written exactly as `payload_from_history` captures them; never hand-edit.
"""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf
import yfinance.cache as yf_cache
from alpha_nodes.providers.yfinance.history import payload_from_history

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "yfinance"
PRICE_SYMBOLS = ["BP.L", "HSBA.L", "VOD.L", "ASML.AS", "SAP.DE", "NESN.SW", "NOVO-B.CO", "AAPL"]
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


def main() -> None:
    """Record every fixture for today's date."""
    yf.config.debug.hide_exceptions = False
    yf_cache.set_cache_location(
        tempfile.mkdtemp()
    )  # fresh tz cache: unknown symbols behave as on a first run
    OUT.mkdir(parents=True, exist_ok=True)
    today = date.today()
    for sym in PRICE_SYMBOLS:
        record(sym, today - timedelta(days=730), today - timedelta(days=1), f"prices_{sym}")
    for sym in FX_SYMBOLS:
        record(sym, today - timedelta(days=365), today - timedelta(days=1), f"fx_{sym}")
    record(SPLIT[0], SPLIT[1], SPLIT[2], f"split_{SPLIT[0]}")
    for name, (sym, start, end) in MISSING_PROBES.items():
        # An unknown symbol answers HTTP 404 until yfinance has cached its missing timezone
        # (observed: the third call), then YFTzMissingError; repeat until the probe's class shows.
        for _ in range(6):
            if record(sym, start, end, name) == WANTED.get(name, None) or name not in WANTED:
                break
    print("yfinance", yf.__version__, "recorded", today)


if __name__ == "__main__":
    main()
