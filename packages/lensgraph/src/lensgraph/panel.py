"""Panels: a named set of lenses wired to an aggregator, as a registry plus run helpers.

See documentation/design/core.md, Verdicts and dossiers.
"""

from typing import ClassVar

from pydantic import BaseModel

from .aggregate import Aggregator, ShrunkMeanAggregator
from .plan import RunResult
from .registry import NodeRegistry
from .verdict import Dossier


class Panel(BaseModel):
    """The lenses whose verdicts are aggregated, and the name of the resulting node."""

    lenses: list[str]  # registered lens node names
    aggregator: str = "dossier"  # node name of the aggregator; the run target
    reviewer: str | None = None  # registered `DossierReviewer` class name, or None for no review

    def targets(self) -> list[str]:
        """Run targets: the aggregator, plus the `review` node when a reviewer is set."""
        return [self.aggregator, *(["review"] if self.reviewer else [])]


def panel_registry(
    panel: Panel,
    registry: NodeRegistry,
    aggregator_cls: type[Aggregator] = ShrunkMeanAggregator,
) -> NodeRegistry:
    """Copy `registry` and add an `aggregator_cls` subclass named `panel.aggregator`.

    If `panel.reviewer` is set, also register that reviewer class (looked up in `registry`)
    under the name `review`, reading the aggregator's dossier.

    Each lens is an optional input (kwarg = lens node name), so one failed lens becomes a
    failed verdict instead of skipping the dossier.
    """

    names_by_node = {lens: getattr(registry.get(lens), "lens_name", lens) for lens in panel.lenses}

    class PanelAggregator(aggregator_cls):
        name: ClassVar[str] = panel.aggregator
        optional_inputs: ClassVar[dict[str, str]] = {lens: lens for lens in panel.lenses}
        lens_names: ClassVar[dict[str, str]] = names_by_node

    copy = NodeRegistry()
    for node_name in registry.names():
        copy.register(registry.get(node_name))
    copy.register(PanelAggregator)
    if panel.reviewer:
        from .graph import GraphError  # lazy: avoid import cycles
        from .review import DossierReviewer

        reviewer_cls = registry.get(panel.reviewer)
        if not issubclass(reviewer_cls, DossierReviewer):
            raise GraphError(
                f"Panel.reviewer {panel.reviewer!r} is a {reviewer_cls.__name__}, "
                "not a DossierReviewer subclass"
            )

        class PanelReviewer(reviewer_cls):  # type: ignore[valid-type, misc]
            name: ClassVar[str] = "review"
            inputs: ClassVar[dict[str, str]] = {"dossier": panel.aggregator}

        copy.register(PanelReviewer)
    return copy


def dossiers(result: RunResult) -> list[Dossier]:
    """All `Dossier` outputs of a run, in candidate order (`result.results` is in plan order)."""
    return [
        v for key in result.results if isinstance(v := result.values.get(key), Dossier)
    ]
