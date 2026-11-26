"""Generic fetch nodes over the source store: per-candidate and shared-scope dataset reads.

Domains subclass `DatasetFetch` / `DatasetFetchMany`, setting `name` and `dataset`; the store
(injected by `arun` as the `sources` service) decides whether the network is needed. These are
`FetchNode`s, so they are never memoized and the hash of the returned slice keys downstream
nodes. See documentation/design/core.md, Source store and Memoization.
"""

from datetime import timedelta
from typing import Any, ClassVar

import pandas as pd
import pandera.pandas as pa
from pydantic import Field

from ..node import FetchNode, NodeContext
from .base import SourceStore
from .clock import SystemClock
from .models import DateInterval

_LIST_COLUMNS = frozenset({"repairs", "quality_reasons"})  # fact meta columns holding lists


def _window(store: Any, ctx: NodeContext, lookback_days: int | None) -> DateInterval | None:
    """The `lookback_days` window ending at `ctx.as_of` or the store clock's today; None for no window."""
    if lookback_days is None:
        return None
    end = ctx.as_of
    if end is None:
        clock = getattr(store, "clock", None) or SystemClock()
        end = clock.now().date()
    return DateInterval(start=end - timedelta(days=lookback_days), end=end)


def _frame_contract(cls: Any) -> Any:
    """The plan-build contract of a dataset fetch class: its `frame_schema` when set, else `output`."""
    return cls.frame_schema if cls.frame_schema is not None else cls.output


def _store(ctx: NodeContext) -> SourceStore:
    """The `sources` service; a clear error when the run has none."""
    try:
        return ctx.services["sources"]
    except KeyError:
        raise KeyError("no 'sources' service: add a `sources:` section to the run config") from None


class DatasetFetch(FetchNode):
    """Per-candidate read of one dataset through `ctx.services["sources"]`; subclasses set `name` and `dataset`.

    Returns the slice frame (canonical plus fact meta columns). A legitimately empty slice is an
    empty frame, not a failure; `SourceUnavailable` propagates and fails the node.

    `frame_schema` (optional, set by the subclass) is the dataset's canonical column model. It is
    what consumers see at plan build (`contract()`), so its columns reach the glossary check and
    data dictionary of AI lenses; the fact meta columns the slice also carries are not part of
    the contract. Runtime output stays a plain frame.

    Args:
        lookback_days: for date-axis datasets, the window runs from `lookback_days` days before
            `ctx.as_of` (or the store clock's today) through that day, both ends included, so it
            spans `lookback_days + 1` calendar days. None reads without a window.
        entity_attr: take the entity from `candidate.attrs[entity_attr]` instead of `candidate.id`.
        include_rejected: also return rows the provider's normaliser marked `rejected`.
    """

    dataset: ClassVar[str]
    output: ClassVar[Any] = pd.DataFrame
    frame_schema: ClassVar[type[pa.DataFrameModel] | None] = None
    lookback_days: int | None = None
    entity_attr: str | None = None
    include_rejected: bool = False

    @classmethod
    def contract(cls) -> Any:
        """The dataset's `frame_schema` when set, else `output`."""
        return _frame_contract(cls)

    async def run(self, ctx: NodeContext) -> pd.DataFrame:  # type: ignore[override]
        """Read this candidate's slice of `dataset`, fetching gaps first."""
        assert ctx.candidate is not None, f"{self.name}: DatasetFetch is per-candidate"
        entity = ctx.candidate.id if self.entity_attr is None else ctx.candidate.attrs.get(self.entity_attr)
        if entity is None:
            raise ValueError(f"{self.name}: candidate {ctx.candidate.id!r} has no attr {self.entity_attr!r}")
        store = _store(ctx)
        slice_ = await store.get(
            self.dataset,
            str(entity),
            _window(store, ctx, self.lookback_days),
            as_of=ctx.as_of,
            include_rejected=self.include_rejected,
        )
        return slice_.frame


class DatasetFetchMany(FetchNode):
    """Shared-scope read of one dataset for a fixed entity list (e.g. FX rates); one `ensure` call, so batching applies.

    Returns the entities' slices concatenated, with an `entity` column, sorted by entity (and
    the dataset's key columns within it).

    `frame_schema` (optional, set by the subclass) is the dataset's canonical column model. It is
    what consumers see at plan build (`contract()`), so its columns reach the glossary check and
    data dictionary of AI lenses; the fact meta columns the slice also carries are not part of
    the contract. Runtime output stays a plain frame.

    Args:
        entities: the entities to read; at least one.
        lookback_days: as for `DatasetFetch`.
    """

    scope: ClassVar = "shared"
    dataset: ClassVar[str]
    output: ClassVar[Any] = pd.DataFrame
    frame_schema: ClassVar[type[pa.DataFrameModel] | None] = None
    entities: list[str] = Field(min_length=1)  # an empty list is a params error at plan time
    lookback_days: int | None = None

    @classmethod
    def contract(cls) -> Any:
        """The dataset's `frame_schema` when set, else `output`."""
        return _frame_contract(cls)

    async def run(self, ctx: NodeContext) -> pd.DataFrame:  # type: ignore[override]
        """Ensure all entities in one store call, then read each slice."""
        store = _store(ctx)
        interval = _window(store, ctx, self.lookback_days)
        await store.ensure(self.dataset, self.entities, interval)
        entities = sorted(set(self.entities))
        slices = {e: store.query(self.dataset, e, interval, as_of=ctx.as_of).frame for e in entities}
        frames = [f.assign(entity=e) for e, f in slices.items() if not f.empty]
        if not frames:  # keep the dataset's columns and dtypes so downstream selections still work
            empty = slices[entities[0]].assign(entity=pd.Series([], dtype=object))
            # the store's empty frames hold strings as object; a non-empty read has them as str
            strings = [c for c in empty.columns if empty[c].dtype == object and c not in _LIST_COLUMNS]
            return empty.astype(dict.fromkeys(strings, "str"))
        return pd.concat(frames, ignore_index=True)
