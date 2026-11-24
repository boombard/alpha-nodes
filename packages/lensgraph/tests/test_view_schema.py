"""Generated artefacts of the RunView contract (TS types, UI fixture) stay in step with Python."""

import os
from pathlib import Path

from lensgraph.view.build import build_run_view, render_run_json
from lensgraph.view.schema import run_view_schema, schema_hash
from toy.toy_view import run_toy_panel

UI = Path(__file__).resolve().parents[2] / "lensgraph-ui"
TYPES = UI / "src" / "types" / "run-view.ts"
FIXTURE = UI / "fixtures" / "toy-run.json"


def test_schema_has_run_view_shape():
    schema = run_view_schema()
    assert {"summary", "plan", "candidates", "cited", "llm_calls"} <= set(schema["properties"])
    assert "schema_version" in schema["required"]  # serialization mode: defaults are present


def test_ts_types_up_to_date():
    first = TYPES.read_text().splitlines()[0]
    assert first == f"// schema-hash: {schema_hash()}", (
        "RunView changed: run `node packages/lensgraph-ui/scripts/gen-types.mjs`"
    )


def test_ui_fixture_up_to_date(tmp_path):
    toy = run_toy_panel(tmp_path / "store")
    index = toy.index()
    try:
        text = render_run_json(build_run_view(toy.run_id, index, toy.blobs()))
    finally:
        index.close()
    if os.environ.get("LENSGRAPH_REGEN_FIXTURES") == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(text)
    assert FIXTURE.read_text() == text, "set LENSGRAPH_REGEN_FIXTURES=1 and rerun to refresh"
