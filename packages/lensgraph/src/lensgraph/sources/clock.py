"""Clocks for the source store: real time in production, controllable in tests.

See documentation/design/core.md, Source store (TTL and backoff depend on time).
"""

import asyncio
from datetime import UTC, datetime, timedelta


class SystemClock:
    """`Clock` over the wall clock and `asyncio.sleep`."""

    def now(self) -> datetime:
        """Current time, tz-aware UTC."""
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        """Sleep for real."""
        await asyncio.sleep(seconds)


class FakeClock:
    """`Clock` for tests and replays: time moves only when told, sleeps return at once."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock start must be tz-aware")
        self._now = start
        self.sleeps: list[float] = []  # every sleep requested, in order

    def now(self) -> datetime:
        """Current fake time."""
        return self._now

    def advance(self, seconds: float) -> None:
        """Move time forward."""
        self._now += timedelta(seconds=seconds)

    async def sleep(self, seconds: float) -> None:
        """Record the request, advance time by `seconds`, and yield once."""
        self.sleeps.append(seconds)
        self.advance(seconds)
        await asyncio.sleep(0)
