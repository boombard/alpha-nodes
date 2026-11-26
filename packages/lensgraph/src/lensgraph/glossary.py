"""Glossary: one Markdown file per term, validated on load, with opt-in prompt notes for AI nodes.

See documentation/design/core.md, Glossary. A domain ships a directory of `<id>.md` entries
(YAML frontmatter plus fixed `##` sections). Humans read the full entry; AI nodes that opt in
(`AINode.glossary_terms`, `AINode.use_glossary`) get only the short prompt note, via
`Glossary.prompt_block`. `Glossary.export` is the contract for a later browser glossary page.
This module is domain-free: it never imports domain code (`check_imports` is the one,
explicit, exception, run from a domain's tests).
"""

import importlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from .hashing import content_hash

SectionKey = Literal[
    "definition",
    "calculation",
    "relevance",
    "shortcomings",
    "provider_notes",
    "similar",
    "sources",
    "prompt_note",
]
"""Fixed section keys; code and the browser use these, the heading text is display only."""

HEADINGS: dict[str, SectionKey] = {
    "Definition": "definition",
    "How we calculate it": "calculation",
    "Why it matters": "relevance",
    "Shortcomings and pitfalls": "shortcomings",
    "Provider notes": "provider_notes",
    "Similar terms": "similar",
    "Sources": "sources",
    "Prompt note": "prompt_note",
}
"""Display heading (`## ...`) to section key."""

_ALWAYS_REQUIRED: tuple[SectionKey, ...] = (
    "definition", "calculation", "relevance", "shortcomings", "similar", "prompt_note",
)
MAX_PROMPT_NOTE_WORDS = 60
MAX_SUMMARY_WORDS = 30
EXPORT_SCHEMA_VERSION = 1

_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_HTML = re.compile(
    r"</?(?![A-Za-z][A-Za-z0-9+.-]*:[^\s>]*>)(?![^\s<>@]+@[^\s<>]+>)[A-Za-z][^>\n]*>|<!--"
)  # tags and comments; CommonMark autolinks (<scheme:...>, <user@host>) are not HTML
_ESCAPED_DOLLAR = re.compile(r"\\\$")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
_IMAGE = re.compile(r"!\[[^\]]*\]\(")


class GlossaryError(ValueError):
    """A glossary entry or directory breaks a rule; the message names the file and the problem."""


class GlossaryEntry(BaseModel):
    """One glossary term: frontmatter fields plus its Markdown sections.

    Field meanings are in core.md, Glossary. `fields` lists result-model fields as
    `Model.field`; `implemented_by` lists dotted paths checked by `Glossary.check_imports`;
    `sections` maps each fixed section key to its Markdown body.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    abbreviations: list[str] = []
    aliases: list[str] = []
    kind: str
    fields: list[str] = []
    implemented_by: list[str] = []
    related: list[str] = []
    status: Literal["draft", "verified"]
    sources: list[str] = []
    summary: str
    category: str
    sections: dict[SectionKey, str]

    @property
    def prompt_note(self) -> str:
        """The short interpretive note inserted into AI prompts (the `prompt_note` section)."""
        return self.sections["prompt_note"].strip()


class GlossaryExport(BaseModel):
    """The browser contract: every entry plus a hash of the whole content (serialised as glossary.json)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int
    content_hash: str
    entries: list[GlossaryEntry]


def _strip_code(text: str) -> str:
    """`text` without fenced or inline code, so code samples can't trip the Markdown checks."""
    return _INLINE_CODE.sub("", _FENCE.sub("", text))


def _split_sections(body: str) -> dict[SectionKey, str]:
    """Split a Markdown body on `## ` headings into section-key -> text; unknown headings raise ValueError."""
    sections: dict[SectionKey, str] = {}
    parts = re.split(r"^## +(.+?)\s*$", body, flags=re.MULTILINE)
    if parts[0].strip():
        raise ValueError("text before the first '##' heading")
    for heading, text in zip(parts[1::2], parts[2::2], strict=True):
        key = HEADINGS.get(heading)
        if key is None:
            raise ValueError(f"unknown section heading {heading!r}; known: {list(HEADINGS)}")
        if key in sections:
            raise ValueError(f"duplicate section {heading!r}")
        sections[key] = text.strip()
    return sections


def _parse_file(path: Path) -> GlossaryEntry:
    """Parse one entry file; raises ValueError (wrapped with the file name by the caller)."""
    text = path.read_text()
    match = re.match(r"---\n(.*?)\n---\n(.*)\Z", text, flags=re.DOTALL)
    if not match:
        raise ValueError("missing YAML frontmatter ('---' block at the top)")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a mapping")  # noqa: TRY004
    try:
        entry = GlossaryEntry(**meta, sections=_split_sections(match.group(2)))
    except ValidationError as exc:
        raise ValueError("; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())) from exc
    _check_entry(entry, path.stem)
    return entry


def _check_entry(entry: GlossaryEntry, stem: str) -> None:
    """Per-entry rules that need no other entry; raises ValueError."""
    if entry.id != stem:
        raise ValueError(f"id {entry.id!r} must equal the file stem {stem!r}")
    required = [*_ALWAYS_REQUIRED, *(["sources"] if entry.status == "verified" else [])]
    sections: dict[str, str] = {str(k): v for k, v in entry.sections.items()}
    for key in required:
        if not sections.get(key, "").strip():
            raise ValueError(f"missing required section {key!r}")
    if entry.status == "verified" and not entry.sources:
        raise ValueError("status 'verified' needs non-empty frontmatter sources")
    if len(entry.summary.split()) > MAX_SUMMARY_WORDS:
        raise ValueError(f"summary is over {MAX_SUMMARY_WORDS} words")
    note = entry.prompt_note
    if len(note.split()) > MAX_PROMPT_NOTE_WORDS:
        raise ValueError(f"prompt note is over {MAX_PROMPT_NOTE_WORDS} words")
    if "$" in _ESCAPED_DOLLAR.sub("", note):
        raise ValueError("prompt note must not contain a formula (math) to apply")
    for key, body in entry.sections.items():
        _check_markdown(key, body)


def _check_markdown(key: str, body: str) -> None:
    """CommonMark-only rules: no raw HTML, no images, balanced `$` math; raises ValueError."""
    plain = _strip_code(body)
    if _HTML.search(plain):
        raise ValueError(f"raw HTML in section {key!r} (CommonMark only)")
    if _IMAGE.search(plain):
        raise ValueError(f"image in section {key!r} (not supported yet)")
    math = _ESCAPED_DOLLAR.sub("", plain)  # a literal dollar sign is written \$
    if math.count("$$") % 2 or math.replace("$$", "").count("$") % 2:
        raise ValueError(f"unbalanced $ math delimiters in section {key!r}")


def _entry_links(entry: GlossaryEntry) -> list[str]:
    """Targets of the relative `*.md` links in an entry's sections (ids, without `.md`)."""
    targets: list[str] = []
    for body in entry.sections.values():
        for target in _LINK.findall(_strip_code(body)):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            path = target.split("#", 1)[0]
            targets.append(path.removesuffix(".md") if path.endswith(".md") else path)
    return targets


class Glossary(BaseModel):
    """A validated set of entries by id. Build with `Glossary.load`; see core.md, Glossary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: dict[str, GlossaryEntry]

    @classmethod
    def load(cls, directory: Path) -> "Glossary":
        """Load and validate every `*.md` in `directory`; `GlossaryError` names file and problem."""
        entries: dict[str, GlossaryEntry] = {}
        for path in sorted(Path(directory).glob("*.md")):
            try:
                entries[path.stem] = _parse_file(path)
            except ValueError as exc:
                raise GlossaryError(f"{path.name}: {exc}") from exc
        glossary = cls(entries=entries)
        glossary._check_cross_references()
        return glossary

    def _check_cross_references(self) -> None:
        """Rules spanning entries: related ids and links resolve, no field is claimed twice."""
        owner: dict[str, str] = {}
        for entry_id, entry in self.entries.items():
            unknown = sorted(set(entry.related) - set(self.entries))
            if unknown:
                raise GlossaryError(f"{entry_id}.md: related ids not in the glossary: {unknown}")
            bad = sorted({t for t in _entry_links(entry) if t not in self.entries})
            if bad:
                raise GlossaryError(f"{entry_id}.md: links to unknown entries: {bad}")
            for field in entry.fields:
                if field in owner:
                    raise GlossaryError(
                        f"{entry_id}.md: field {field!r} is already claimed by {owner[field]!r}"
                    )
                owner[field] = entry_id

    def check_imports(self) -> list[str]:
        """The `implemented_by` dotted paths that do not import or resolve (a domain test asserts `[]`)."""
        missing: list[str] = []
        for entry in self.entries.values():
            missing.extend(p for p in entry.implemented_by if not _resolves(p))
        return missing

    def by_field(self) -> dict[str, str]:
        """`"Model.field"` -> entry id, for attaching a term to a cited output field."""
        return {f: e.id for e in self.entries.values() for f in e.fields}

    def _select(self, ids: Iterable[str]) -> list[GlossaryEntry]:
        """Entries for `ids`, sorted by id; unknown ids raise `GlossaryError`."""
        wanted = sorted(set(ids))
        unknown = [i for i in wanted if i not in self.entries]
        if unknown:
            raise GlossaryError(f"unknown glossary ids: {unknown}")
        return [self.entries[i] for i in wanted]

    def prompt_block(self, ids: Iterable[str]) -> str:
        """The deterministic "## Terms" prompt block for `ids`: `**Name (ABBR)**: note`, sorted by id.

        Notes have `\\$` unescaped to `$` (the escape only matters to the browser's math renderer).
        """
        lines = ["## Terms", ""]
        for entry in self._select(ids):
            label = entry.name + (f" ({', '.join(entry.abbreviations)})" if entry.abbreviations else "")
            lines.append(f"**{label}**: {entry.prompt_note.replace(chr(92) + '$', '$')}")
            lines.append("")
        return "\n".join(lines)

    def content_hash(self, ids: Iterable[str]) -> str:
        """Hash of the full content of the entries `ids` (any edit to them changes it)."""
        return content_hash([e.model_dump(mode="json") for e in self._select(ids)])

    def export(self) -> "GlossaryExport":
        """All entries, sorted by id, with a content hash: the browser contract (`glossary.json`)."""
        ids = sorted(self.entries)
        return GlossaryExport(
            schema_version=EXPORT_SCHEMA_VERSION,
            content_hash=self.content_hash(ids),
            entries=[self.entries[i] for i in ids],
        )


def _resolves(dotted: str) -> bool:
    """Whether `pkg.mod.attr[.attr]` imports: longest importable module prefix, then attributes."""
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            obj: Any = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for attr in parts[cut:]:
            if not hasattr(obj, attr):
                return False
            obj = getattr(obj, attr)
        return True
    return False
