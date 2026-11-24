"""JSON Schema of `RunView` and the hash that ties the generated TypeScript types to it.

See documentation/design/core.md, Reporting. `packages/lensgraph-ui/scripts/gen-types.mjs`
calls `main()` here and writes `schema_hash()` into
the first line of `run-view.ts`; a Python test compares the two, so it needs no Node.
"""

import hashlib
import json
from typing import Any

from .models import RunView


def run_view_schema() -> dict[str, Any]:
    """JSON Schema of `RunView` in serialization mode (defaulted fields count as present)."""
    return RunView.model_json_schema(mode="serialization")


def schema_hash() -> str:
    """Short, stable hash of `run_view_schema()`; changes whenever the contract changes."""
    canonical = json.dumps(run_view_schema(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def main() -> None:
    """Print `{"hash": ..., "schema": ...}` as JSON; the input of `scripts/gen-types.mjs`."""
    print(json.dumps({"hash": schema_hash(), "schema": run_view_schema()}))
