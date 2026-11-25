"""Snapshot TA-Lib's per-function docs into `documentation/reference/ta-lib/` (TASK-42).

Maintenance script (network use is fine here, like `record_yfinance_fixtures.py`; tests never
call it). Pages are written **verbatim**: the formulas and conventions are the point, so nothing
is summarised or rewritten. The README index is generated from the pages plus the pinned
ta-lib-python wrapper (see documentation/design/finance.md, Technical analysis and TA-Lib).

    uv run python packages/alpha_nodes/scripts/sync_talib_reference.py [--commit SHA]

Without `--commit`, TA-Lib `main` HEAD is resolved to a SHA and pinned. The parsing and
rendering functions are pure and unit-tested; only `main` and its helpers touch the network.
"""

import argparse
import json
import re
import urllib.request
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel

REPO = "TA-Lib/ta-lib"
PAGES_PATH = "website/src/functions"
OUT = Path(__file__).resolve().parents[3] / "documentation" / "reference" / "ta-lib"
UNGROUPED = "Ungrouped"

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_GROUP_LINK = re.compile(r"ta-lib-python/func_groups/([a-z_]+)\.html")


class TalibParam(BaseModel):
    """One optional input parameter of a TA-Lib function, e.g. `timePeriod` default `30`."""

    name: str
    """Parameter name without the `optIn` prefix, first letter lowercased (the wrapper's kwarg)."""
    default: str


class TalibFunction(BaseModel):
    """A parsed reference page: just the fields the README index needs."""

    name: str
    """Upper-case function name as the wrapper spells it (`SMA`); also the page stem uppercased."""
    title: str
    description: str
    """The page's frontmatter `description`, verbatim."""
    inputs: list[str]
    outputs: list[str]
    params: list[TalibParam]
    page_group: str | None
    """Group read from the page's ta-lib-python link, used only if the wrapper lacks the function."""


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:]


def _strip_prefix(name: str, prefix: str) -> str:
    return _lower_first(name.removeprefix(prefix))


def _section(body: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", body, re.DOTALL | re.MULTILINE
    )
    return match.group(1) if match else ""


def _frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER.match(text)
    fields: dict[str, str] = {}
    for line in (match.group(1) if match else "").splitlines():
        key, _, value = line.partition(":")
        if value:
            fields[key.strip()] = (
                json.loads(value.strip()) if value.strip().startswith('"') else value.strip()
            )
    return fields


def _bullet_names(section: str, prefix: str) -> list[str]:
    return [_strip_prefix(m, prefix) for m in re.findall(r"^- `(\w+)`", section, re.MULTILINE)]


def parse_page(stem: str, text: str) -> TalibFunction:
    """Parse a verbatim TA-Lib page (frontmatter, Inputs, Outputs, Parameters) for the index."""
    front = _frontmatter(text)
    params: list[TalibParam] = []
    for row in _section(text, "Parameters").splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].startswith("`"):
            params.append(
                TalibParam(name=_strip_prefix(cells[0].strip("`"), "optIn"), default=cells[2])
            )
    group = _GROUP_LINK.search(text)
    return TalibFunction(
        name=stem.upper(),
        title=front.get("title", stem),
        description=front.get("description", ""),
        inputs=_bullet_names(_section(text, "Inputs"), "in"),
        outputs=_bullet_names(_section(text, "Outputs"), "out"),
        params=params,
        page_group=group.group(1).replace("_", " ").title() if group else None,
    )


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def render_index(
    functions: Sequence[TalibFunction],
    wrapper_groups: Mapping[str, Sequence[str]],
    wrapper_version: str,
) -> str:
    """Render the grouped markdown index table.

    The group comes from the wrapper (`talib.get_function_groups()`) when it knows the function,
    else from the page's own ta-lib-python link, else "Ungrouped" (never guessed).
    `wrapper_version` (`talib.__version__`) labels the last column.
    """
    by_wrapper = {fn: group for group, fns in wrapper_groups.items() for fn in fns}
    grouped: dict[str, list[TalibFunction]] = defaultdict(list)
    for f in functions:
        grouped[by_wrapper.get(f.name) or f.page_group or UNGROUPED].append(f)
    lines: list[str] = []
    for group in sorted(grouped, key=lambda g: (g == UNGROUPED, g)):
        lines += [
            f"### {group}",
            "",
            f"| Function | Title | Description | Inputs | Params (defaults) | in ta-lib-python {wrapper_version} |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for f in sorted(grouped[group], key=lambda f: f.name):
            params = ", ".join(f"{p.name}={p.default}" for p in f.params) or "none"
            in_wrapper = "yes" if f.name in by_wrapper else "no"
            lines.append(
                f"| [{f.name}](functions/{f.name.lower()}.md) | {_cell(f.title)} "
                f"| {_cell(f.description)} | {', '.join(f.inputs)} | {_cell(params)} | {in_wrapper} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_readme(
    index: str,
    sha: str,
    fetched: date,
    licence: str,
    pages: int,
    count: int,
    in_wrapper: int,
    wrapper_version: str,
) -> str:
    """Render the reference README: provenance, licence, refresh instructions and the index."""
    return f"""# TA-Lib function reference

A verbatim local snapshot of TA-Lib's per-function documentation, for agents choosing or
specifying technical indicators (formula, inputs, params, defaults, notes). Design context:
[finance.md, Technical analysis and TA-Lib](../../design/finance.md). TA-Lib is also a dev
dependency, used as a test oracle for our own calcs.

- Source: https://github.com/{REPO}/tree/{sha}/{PAGES_PATH}
- Commit: `{sha}`
- Fetched: {fetched.isoformat()}
- Pages: {pages} in [functions/](functions/), of which {count} are functions (the rest,
  `index.md` and `stability.md`, are prose); {in_wrapper} functions are exposed by the pinned
  ta-lib-python {wrapper_version} (`talib.get_functions()`). The docs on TA-Lib `main` can run ahead of
  the released wrapper: pages marked `no` below are kept but cannot be called from Python.
- Pages are unmodified, so chart links, CSV links and `/functions/...` links inside them
  point at the TA-Lib website, not at this repo. The reference CSVs and SVGs are not stored.

## Licence

TA-Lib is BSD-3-Clause. Notice, reproduced from the source repository's `LICENSE`:

```text
{licence.strip()}
```

## Refresh

```sh
uv run python packages/alpha_nodes/scripts/sync_talib_reference.py [--commit SHA]
```

Without `--commit` the script pins current `main` HEAD. It rewrites `functions/*.md` and this
file; review the diff and bump the ta-lib-python pin in the root `pyproject.toml` if the
wrapper has moved. Never hand-edit the pages.

## Index

Columns: inputs are the page's input series (`real` is a generic series); params show
`name=default`. Group is the wrapper's where it knows the function, else the page's.

{index}"""


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def _resolve_sha(commit: str | None) -> str:
    ref = commit or "main"
    return json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/{ref}"))["sha"]


def main() -> None:
    """Fetch the pages at the chosen commit, write them verbatim and regenerate the README."""
    import talib

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", help="TA-Lib commit SHA (default: current main HEAD)")
    sha = _resolve_sha(parser.parse_args().commit)
    listing = json.loads(
        _get(f"https://api.github.com/repos/{REPO}/contents/{PAGES_PATH}?ref={sha}")
    )
    stems = sorted(Path(e["name"]).stem for e in listing if e["name"].endswith(".md"))
    raw = f"https://raw.githubusercontent.com/{REPO}/{sha}"
    out_dir = OUT / "functions"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):
        old.unlink()
    functions: list[TalibFunction] = []
    for stem in stems:
        text = _get(f"{raw}/{PAGES_PATH}/{stem}.md").decode("utf-8")
        (out_dir / f"{stem}.md").write_text(text, encoding="utf-8")
        if "\n## Inputs\n" in text:  # index.md and stability.md are prose, not functions
            functions.append(parse_page(stem, text))
    wrapper_groups = talib.get_function_groups()
    index = render_index(functions, wrapper_groups, talib.__version__)
    wrapped = set(talib.get_functions())
    readme = render_readme(
        index,
        sha,
        date.today(),
        _get(f"{raw}/LICENSE").decode("utf-8"),
        len(stems),
        len(functions),
        sum(f.name in wrapped for f in functions),
        talib.__version__,
    )
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"wrote {len(functions)} pages at {sha}")


if __name__ == "__main__":
    main()
