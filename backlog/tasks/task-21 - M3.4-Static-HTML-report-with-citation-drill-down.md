---
id: TASK-21
title: M3.4 Static HTML report with citation drill-down
status: To Do
assignee: []
created_date: '2026-11-23T23:51:15Z'
labels:
  - core
milestone: m-2
dependencies:
  - TASK-19
  - TASK-20
references:
  - documentation/design/core.md
type: feature
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Static HTML report. Spec: `documentation/design/core.md`, Reporting (static, self-contained, one folder per run, citations link to rendered views, domain renderers).

## Files
- Create: `packages/lensgraph/src/lensgraph/report/{__init__,builder,renderers}.py`, `packages/lensgraph/src/lensgraph/report/templates/{base,index,candidate,cited}.html.j2`, `packages/lensgraph/src/lensgraph/report/static/report.css`
- Modify: `packages/lensgraph/src/lensgraph/__init__.py` (export `build_report`), `packages/lensgraph/pyproject.toml` (package data for templates/static, if hatch needs it)
- Test: `packages/lensgraph/tests/test_report.py`

## Interfaces
Consumes: `DossierRecord`, `DossierReview`, `LLMCall`, `RunIndex` (`run_config`, `node_result`, `llm_calls`, `node_results`), `BlobStore`, `resolve_all`/`CitedValue`/`UnresolvedCitation` (M3.2), `to_mermaid`, `resolve_classes`, `NodeRegistry`, `Panel`.

Produces:
```python
# renderers.py
Renderer = Callable[[Any, int], str]                 # (value, max_rows) -> HTML fragment (escaped)
class RendererRegistry:
    def register(self, type_: type, renderer: Renderer) -> None    # most specific type wins (MRO order)
    def render(self, value: Any, max_rows: int = 200) -> str
DEFAULT_RENDERERS: RendererRegistry                  # DataFrame -> table (last max_rows rows + note), BaseModel -> JSON <pre>,
                                                     # list of models -> table of model fields, scalar -> text
# builder.py
def load_records(run_id: str, index: RunIndex, blobs: BlobStore) -> list[DossierRecord]
    # panel/aggregator from run_config; per candidate: aggregator node_result -> blob -> Dossier; "review" node -> DossierReview if present
def build_report(run_id: str, index: RunIndex, blobs: BlobStore, out_dir: Path, *,
                 registry: NodeRegistry | None = None, renderers: RendererRegistry = DEFAULT_RENDERERS,
                 max_rows: int = 200) -> Path        # returns out_dir / "index.html"
```
Semantics:
- **Layout:** `index.html` (run summary), `candidates/<id>.html` (one per candidate), `cited/<source_hash>.html` (one per distinct cited blob, deduplicated), `dossiers/<id>.json` (`DossierRecord`, indented), `report.css`.
- **Run summary:** run id, status, started/finished, config (pretty YAML or JSON), node counts by status, cache hit rate, LLM calls with total tokens and total cost (shown as "unknown" if any call's cost is None, never a partial total presented as complete), and the candidate table: id, overall stance, direction, evidence share, agreement, per-lens status, review flags.
- **Candidate page:** the dossier headline (overall, direction, evidence share, agreement); per verdict: status, stance and stance_mean, conviction, coverage with input sufficiency, components, error, provenance (model, prompt hash, tokens); claims with each cite as a link to its `cited/` page (an `UnresolvedCitation` renders as a visible "unresolved" marker, never a crash); flags; the review (summary, fit, gaps, flags) when present.
- **Graph:** `to_mermaid` over the panel's resolved classes when `registry` is given, embedded as `<pre class="mermaid">` with Mermaid loaded from a pinned jsDelivr URL; offline, the diagram source text still shows.
- **Escaping:** everything rendered goes through Jinja2 autoescape; LLM text is untrusted.
- **Size:** embed only cited data plus summaries (frames capped at `max_rows`).

## Steps
- [ ] Write the failing tests (run the toy panel with reviewer into a `tmp_path` store first, in a module fixture):
  - `test_report_layout`: index, one page per candidate, cited pages, dossier JSON files exist.
  - `test_index_lists_candidates_with_headline_numbers`: S1 to S3 rows; S3 shows no overall stance.
  - `test_claim_links_to_cited_page`: a growth claim's link target exists and contains the rendered value.
  - `test_unresolved_citation_marked_not_raised`: delete a cited blob, rebuild, page shows "unresolved".
  - `test_llm_cost_total_unknown_when_any_none`
  - `test_html_escapes_llm_text`: a claim text containing `<script>` appears escaped.
  - `test_renderer_registry_most_specific_wins` and `test_frame_renderer_caps_rows`
  - `test_dossier_json_is_dossier_record`
  - Assert structure (element ids/classes, links), not pixels or whole-file snapshots.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_report.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): static HTML report with citation drill-down`.

Out of scope: CLI wiring (M3.5), domain renderers (finance milestones), charts beyond the renderer hook.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Report folder has index, candidate pages, deduplicated cited pages and DossierRecord JSON
- [ ] #2 Every claim citation links to a rendered view of its stored value; unresolved citations are marked, never crash
- [ ] #3 Run summary shows LLM token totals and cost, 'unknown' when any call's cost is unknown
- [ ] #4 All rendered text is escaped; renderer registry picks the most specific type
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
