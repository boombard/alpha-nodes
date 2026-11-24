"""Toy post-panel reviewer over the strain domain."""

from pathlib import Path
from typing import ClassVar

from lensgraph.review import DossierReviewer

_PROMPTS = Path(__file__).parent / "prompts"


class ToyReviewer(DossierReviewer):
    """Reviews a strain dossier against the pilot brief."""

    name: ClassVar[str] = "toy_reviewer"  # `panel_registry` re-registers it as node "review"
    prompt: ClassVar[Path] = _PROMPTS / "reviewer.md.j2"


toy_reviewer = ToyReviewer
