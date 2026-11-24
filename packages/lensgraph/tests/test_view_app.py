"""The committed run view bundle is installable and in step with the UI sources (no Node needed)."""

import hashlib
import json
import re
from pathlib import Path

from lensgraph.view import install_app

UI = Path(__file__).resolve().parents[2] / "lensgraph-ui"
APP = Path(__file__).resolve().parents[1] / "src" / "lensgraph" / "view" / "app"
ROOT_FILES = ("package.json", "pnpm-lock.yaml", "index.html", "vite.config.ts", "tsconfig.json")


def ui_source_hash() -> str:
    """Hash of everything that shapes the bundle; must match `scripts/bundle.mjs`.

    Covers the root files above and all of `src/**` (tests live in `tests/`, outside the hash),
    each as `relative/path NUL bytes NUL` in sorted path order.
    """
    paths = [UI / name for name in ROOT_FILES]
    paths += [p for p in (UI / "src").rglob("*") if p.is_file()]
    digest = hashlib.sha256()
    for p in sorted(paths, key=lambda p: p.relative_to(UI).as_posix()):
        digest.update(p.relative_to(UI).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return digest.hexdigest()


def test_install_app_copies_the_bundle(tmp_path):
    out = tmp_path / "report"
    path = install_app(out)
    assert path == out / "index.html"
    assert path.read_bytes() == (APP / "index.html").read_bytes()
    assert b"<div id=\"root\">" in path.read_bytes()


def test_bundle_is_self_contained():
    html = (APP / "index.html").read_text()
    assert 'src="data/run.js"' in html  # embedded data, loaded before the app
    assert "<link" not in html  # styles are inlined
    assert not re.search(r'<script[^>]+src="(?!data/run\.js)', html)  # no external scripts


def test_build_info_up_to_date():
    info = json.loads((APP / "BUILD_INFO.json").read_text())
    assert info["source_hash"] == ui_source_hash(), (
        "UI sources changed: run `pnpm -C packages/lensgraph-ui bundle` and commit the result"
    )
    assert info["built_at"]
