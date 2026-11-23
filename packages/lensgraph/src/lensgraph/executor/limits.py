"""Per-resource concurrency and rate limits; see documentation/design/core.md, Execution."""

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from pydantic import BaseModel, ConfigDict


class ResourceLimit(BaseModel):
    """Limits for one named resource (a `Node.resource`, e.g. a data or LLM provider)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concurrency: int = 4  # max simultaneous holders of a slot
    per_second: float | None = None  # max slot acquisitions per second; None means unpaced


class _Pool:
    """Semaphore plus even pacing of acquisitions for one resource."""

    def __init__(self, limit: ResourceLimit) -> None:
        self._sem = asyncio.Semaphore(limit.concurrency)
        self._interval = 1.0 / limit.per_second if limit.per_second else 0.0
        self._next_start = 0.0
        self._lock = asyncio.Lock()

    async def _pace(self) -> None:
        """Wait until this acquisition's turn: starts are spaced `1/per_second` apart."""
        if not self._interval:
            return
        loop = asyncio.get_running_loop()
        async with self._lock:
            now = loop.time()
            start = max(now, self._next_start)
            self._next_start = start + self._interval
        if start > now:
            await asyncio.sleep(start - now)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._sem:
            await self._pace()
            yield


class ResourceLimiter:
    """Hands out slots per named resource, enforcing each resource's `ResourceLimit`.

    The executor wraps every node run in `slot(node.resource)`. Create one per event loop
    (asyncio primitives are loop-bound); `AsyncioExecutor` builds a fresh one per `execute`.
    """

    def __init__(self, limits: Mapping[str, ResourceLimit]) -> None:
        self._pools = {name: _Pool(limit) for name, limit in limits.items()}

    def slot(self, resource: str | None) -> AbstractAsyncContextManager[None]:
        """Async context manager holding a slot of `resource`; None or unknown means no limit."""
        pool = self._pools.get(resource) if resource is not None else None
        return pool.slot() if pool else _no_limit()


@asynccontextmanager
async def _no_limit() -> AsyncIterator[None]:
    yield
