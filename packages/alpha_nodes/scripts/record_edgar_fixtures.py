"""Live recorder for the EDGAR test fixtures (the one sanctioned network use; see TASK-51).

Run once, commit the output, never import from tests:
    ALPHA_NODES_SEC_USER_AGENT="<descriptive UA with contact>" \
        uv run python packages/alpha_nodes/scripts/record_edgar_fixtures.py [--force]
SEC requires a descriptive User-Agent; it is read from the environment and never written to
disk. Records the company facts of AAPL (September fiscal year), KO (December) and LAKE
(a small cap, January fiscal year) exactly as served, gzipped, plus the matching subset of
`company_tickers.json`. Existing files are kept unless `--force`. Never hand-edit.
"""

import argparse
import gzip
import json
import os
import time
from datetime import date
from pathlib import Path

from alpha_nodes.providers.edgar.provider import TICKERS_URL, companyfacts_url, get_bytes

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "edgar"
SYMBOLS = ["AAPL", "KO", "LAKE"]
_PAUSE_S = 0.5  # well under SEC's 10 requests/s


def write_gz(name: str, raw: bytes) -> None:
    """Write `raw` (JSON bytes) gzipped, reproducibly (no embedded timestamp)."""
    (OUT / name).write_bytes(gzip.compress(raw, mtime=0))
    print(f"{name}: {len(raw):,} bytes served")


def main() -> None:
    """Record the tickers subset and each symbol's company facts that is not on disk yet."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-record existing files")
    args = parser.parse_args()
    user_agent = os.environ.get("ALPHA_NODES_SEC_USER_AGENT", "").strip()
    if not user_agent:
        parser.error("ALPHA_NODES_SEC_USER_AGENT is not set")
    OUT.mkdir(parents=True, exist_ok=True)
    tickers = json.loads(get_bytes(TICKERS_URL, user_agent))
    subset = {k: v for k, v in tickers.items() if v["ticker"] in SYMBOLS}
    missing = set(SYMBOLS) - {v["ticker"] for v in subset.values()}
    if missing:
        raise SystemExit(f"not in company_tickers.json: {sorted(missing)}")
    write_gz("company_tickers.json.gz", json.dumps(subset).encode())
    for entry in subset.values():
        name = f"companyfacts_{entry['ticker']}.json.gz"
        if (OUT / name).exists() and not args.force:
            continue
        time.sleep(_PAUSE_S)
        write_gz(name, get_bytes(companyfacts_url(int(entry["cik_str"])), user_agent))
    print("recorded", date.today(), "->", SYMBOLS)


if __name__ == "__main__":
    main()
