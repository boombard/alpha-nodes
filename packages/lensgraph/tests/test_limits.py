"""Tests for the per-resource concurrency and rate limiter."""

import asyncio
import time

from lensgraph.executor.limits import ResourceLimit, ResourceLimiter


async def test_per_second_rate():
    limiter = ResourceLimiter({"api": ResourceLimit(concurrency=10, per_second=10)})
    start = time.monotonic()
    for _ in range(5):
        async with limiter.slot("api"):
            pass
    assert time.monotonic() - start >= 0.4


async def test_concurrency_cap_enforced():
    limiter = ResourceLimiter({"api": ResourceLimit(concurrency=2)})
    active = 0
    peak = 0

    async def work() -> None:
        nonlocal active, peak
        async with limiter.slot("api"):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1

    await asyncio.gather(*(work() for _ in range(6)))
    assert peak == 2


async def test_none_and_unknown_resources_are_unlimited():
    limiter = ResourceLimiter({})
    async with limiter.slot(None), limiter.slot("nope"):
        pass
