"""The finance glossary: Markdown entries, one per term, shipped as package data.

The AI lenses set `glossary = FINANCE_GLOSSARY_DIR`; their data dictionary is derived from their
inputs at plan build. See documentation/design/finance.md, Glossary, and core.md, Glossary.
"""

from pathlib import Path

FINANCE_GLOSSARY_DIR = Path(__file__).parent
"""Directory of the finance glossary entries (`<id>.md`); nothing is loaded at import."""
