---
id: TASK-63
title: >-
  Glossary mechanism: entry model, loader, validation, export, opt-in prompt
  notes
status: To Do
assignee: []
created_date: '2026-11-26T00:27:59Z'
updated_date: '2026-11-26T00:28:12Z'
labels:
  - core
milestone: m-5
dependencies: []
references:
  - documentation/design/core.md
type: feature
ordinal: 63000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The domain-free glossary mechanism (core.md "Glossary", added by this task): entry model and loader with
validation, a deterministic prompt block, opt-in insertion into AI-node system prompts (per profile, overridable
per node), the prompt hash covering the inserted text, and a `lensgraph glossary` CLI listing entries by status.
A toy glossary in the lensgraph tests exercises it. No finance content.

## Files
- Create: `packages/lensgraph/src/lensgraph/glossary.py` (`GlossaryEntry`, `Glossary`, `GlossaryError`)
- Modify: `packages/lensgraph/src/lensgraph/ai.py` (`glossary`, `glossary_terms`, `use_glossary`, system prompt and
  prompt hash), `packages/lensgraph/src/lensgraph/llm.py` (`LLMProfile.glossary`; `local` true),
  `packages/lensgraph/src/lensgraph/cli.py` (`glossary` command), `documentation/design/core.md` (new section A)
- Create (test data): `packages/lensgraph/tests/toy/glossary/` (3 toy entries)
- Test: `packages/lensgraph/tests/test_glossary.py`, `packages/lensgraph/tests/test_ai_node.py` (or the existing
  AINode test module), `packages/lensgraph/tests/test_cli.py`

## Interfaces
Produces:
```python
class GlossaryError(ValueError)                       # names the file and the problem
class GlossaryEntry(BaseModel):                       # frozen, extra="forbid"
    id: str; name: str; abbreviations: list[str] = []; aliases: list[str] = []
    kind: str; fields: list[str] = []; implemented_by: list[str] = []; related: list[str] = []
    status: Literal["draft", "verified"]; sources: list[str] = []
    summary: str; category: str
    sections: dict[SectionKey, str]                   # fixed keys (definition, calculation, ...) -> Markdown
    @property prompt_note -> str
class Glossary(BaseModel):
    entries: dict[str, GlossaryEntry]
    @classmethod load(directory: Path) -> Glossary    # GlossaryError on any rule in core.md, incl. raw HTML,
                                                      # unbalanced $ math, unresolved relative .md links
    def check_imports(self) -> list[str]              # unresolved implemented_by paths
    def export(self) -> GlossaryExport                # schema_version, content_hash, entries (browser contract)
    def by_field(self) -> dict[str, str]              # "Model.field" -> id
    def prompt_block(self, ids: Iterable[str]) -> str
    def content_hash(self, ids: Iterable[str]) -> str
# AINode
glossary: ClassVar[Glossary | None] = None
glossary_terms: ClassVar[frozenset[str]] = frozenset()   # __init_subclass__: unknown id -> GlossaryError
use_glossary: bool | None = None                          # param; None = profile default
# LLMProfile
glossary: bool = False
```
CLI: `lensgraph glossary DIR` prints `status  id  fields` sorted draft-first; exit 1 with the error on invalid.

## Steps
- [ ] Failing tests: `test_load_toy_glossary`, `test_id_must_match_stem`, `test_missing_required_section_rejected`,
  `test_unknown_related_rejected`, `test_verified_needs_sources`, `test_field_claimed_twice_rejected`,
  `test_prompt_note_length_capped`, `test_prompt_block_sorted_and_stable`, `test_check_imports_reports_unresolved`,
  `test_raw_html_rejected`, `test_unbalanced_math_rejected`, `test_relative_links_must_resolve`,
  `test_sections_keyed_by_fixed_keys`, `test_export_is_stable_and_hashes_content`;
  AINode: `test_glossary_off_by_default_on_dev`, `test_profile_glossary_on_adds_block_after_static_prompt`,
  `test_node_param_overrides_profile`, `test_glossary_edit_changes_prompt_hash_and_memo_salt`,
  `test_unused_entry_edit_does_not_change_hash`, `test_unknown_glossary_term_rejected_at_class_definition`,
  `test_provenance_records_glossary_terms`; CLI: `test_glossary_command_lists_drafts_first`,
  `test_glossary_command_fails_on_invalid`.
- [ ] Run them. Expected: FAIL.
- [ ] Implement; write core.md section A.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS.
- [ ] Commit: `feat(lensgraph): glossary entries, validation and opt-in prompt notes for AI nodes`.

Out of scope: finance entries (TASK-64); the browser glossary page, run-view term links and embedding entries in
run.json (a later UI task, built on `export()`); retrieval of terms by text match (selection is declared per lens).

Design text for core.md section "Glossary" (write it in this task, verbatim apart from wording fixes): the approved draft, copied below.

## A. core.md: new section "Glossary (user decision, 2026-11-26)", after "AI nodes (guard rails)"

A domain ships a **glossary**: a directory of Markdown files, one per term, each with YAML
frontmatter. It has two readers:

- **Humans**: what a term means, how we compute it, why it matters, where it misleads.
- **AI nodes (opt-in)**: a short prompt note per term, inserted into the system prompt to
  disambiguate terms for weaker models. The note is interpretive guidance only; the model never
  computes (AI nodes, guard rails).

It is the single home of per-term definitions. Design docs keep policy (why a convention was
chosen) and link to entries; kernel and field docstrings point to their entry.

**Entry file** `<id>.md` (the file stem is the id, kebab-case):

```yaml
---
id: fcf                       # = file stem
name: Free cash flow
abbreviations: [FCF]
aliases: [free cash flow to equity (loosely)]
kind: money                   # free text, domain-defined (money, ratio, growth, count, date, ...)
fields: [CashGenerationResult.fcf]     # result-model fields that report this term ("Model.field")
implemented_by: [alpha_nodes.nodes.fundamental_calcs._fcf]   # dotted paths; must import
related: [owner-earnings, fcf-conversion]                    # other ids; must exist
status: draft                 # draft (written from model knowledge) | verified (researched)
sources: []                   # required non-empty when status is verified
---
```

Frontmatter also carries `summary` (one human sentence, ≤ 30 words: the tooltip text) and
`category` (navigation group, domain-defined, e.g. profitability, leverage, valuation, price).

Body sections, in this order (`##` headings; required unless marked optional). Each heading maps
to a fixed section key, which is what code and the browser use; the heading text is display only:
Definition (`definition`) · How we calculate it (`calculation`) · Why it matters (`relevance`) ·
Shortcomings and pitfalls (`shortcomings`) · Provider notes (`provider_notes`, optional) ·
Similar terms (`similar`) · Sources (`sources`, optional while draft) · Prompt note (`prompt_note`).
The Prompt note is at most ~60 words and must not contain a formula to apply.

**Browser-ready format** (so a glossary page and run-view links can be added later without
reformatting entries):
- Bodies are CommonMark only: no raw HTML, no templating, no images for now.
- Formulas use KaTeX-compatible math: inline `$...$`, display `$$...$$` (readable as plain text in
  an editor; rendered in the browser). Delimiters must balance (validated).
- Links between entries are relative Markdown links, `[owner earnings](owner-earnings.md)`: they
  work in editors and on GitHub, and the browser rewrites `*.md` to its own route. Every link must
  resolve to an entry (validated).
- `Glossary.export() -> GlossaryExport` is the contract for the browser, the same pattern as
  RunView: a pydantic model (`schema_version`, `content_hash`, entries with frontmatter, `summary`,
  and sections as Markdown strings keyed by section key), serialised to `glossary.json`; its TS
  types are generated like RunView's when the UI work happens.
- Field linking needs nothing new: entries list `fields` as `ResultModel.field`, and the run-view
  builder knows each cited output's model, so it can attach the term id to a field cite.
- Later (not now): a standalone glossary page in the run view app, term links and tooltips on
  cited fields, and `run.json` embedding the subset of entries a run cited (with the
  `content_hash`), so an old report shows the definitions as they were when it ran.

**Mechanics (lensgraph, domain-free):**

- `GlossaryEntry` (pydantic: frontmatter fields + `sections: dict[str, str]`) and
  `Glossary.load(directory) -> Glossary` validate everything above: id = stem, required
  headings present, `related` ids exist, `sources` non-empty for `verified`, no field claimed by
  two entries, prompt note length. `implemented_by` resolution is checked by
  `Glossary.check_imports()` (a test calls it; loading never imports domain code).
- `Glossary.prompt_block(ids) -> str`: "## Terms" then, per id in sorted order,
  `**<name> (<abbreviations>)**: <prompt note>`. Deterministic.
- `AINode` gains `glossary: ClassVar[Glossary | None] = None` and
  `glossary_terms: ClassVar[frozenset[str]] = frozenset()` (unknown ids raise at class
  definition), and a param `use_glossary: bool | None = None` (None = the profile's default).
  `LLMProfile` gains `glossary: bool = False` (`local` defaults to true; `dev`, `quality` false).
  When on, the block is appended to the system prompt after the template's static content, so it
  stays static per lens and prompt caching still applies.
- **Hashing:** the prompt hash is the hash of the rendered system prompt (template + glossary
  block), so editing an entry the lens uses reruns that lens and nothing else. Provenance
  records `prompt_hash` and `glossary_terms` used (empty when off).
- `lensgraph glossary DIR` lists entries by status (draft first) with their fields, and exits
  non-zero on a validation error.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Glossary.load validates entries as core.md specifies, with GlossaryError naming file and problem
- [ ] #2 AI nodes insert the prompt notes of their declared terms only when on (profile default, node override), after the static template; off by default on dev
- [ ] #3 The prompt hash covers the inserted text: editing a used entry reruns the lens, an unused one does not
- [ ] #4 lensgraph glossary DIR lists entries by status and fails on invalid ones; lensgraph stays domain-free
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
