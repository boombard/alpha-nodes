"""Provider scheduler and shared limiter: batching, pacing, pauses, thresholds, delivery."""

import itertools
import random
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime

import pytest
from lensgraph.sources import (
    Dataset,
    FakeClock,
    FetchOutcome,
    OutcomeKind,
    Provider,
    RateLimitPolicy,
    WorkItem,
)
from lensgraph.sources.base import Clock
from lensgraph.sources.models import DateInterval
from lensgraph.sources.scheduler import ProviderLimiter, run_items
from lensgraph.types import GlobalFailure
from toy.sources_catalog import ASSAYS, FakeAssayProvider, FakeBulkAssayProvider


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 1, 1, tzinfo=UTC))


@pytest.fixture(params=[FakeAssayProvider, FakeBulkAssayProvider], ids=["fake", "bulk"])
def provider(request: pytest.FixtureRequest) -> FakeAssayProvider | FakeBulkAssayProvider:
    return request.param()


def set_policy(provider: Provider, **policy: object) -> None:
    """Replace the provider's declared rate-limit policy fields (tests tune limits per scenario)."""
    caps = provider.capabilities
    provider.capabilities = caps.model_copy(
        update={"rate_limit": caps.rate_limit.model_copy(update=policy)}
    )


def make_items(n: int, params: dict[str, str] | None = None) -> list[WorkItem]:
    interval = DateInterval(start=date(2026, 1, 1), end=date(2026, 1, 3))
    return [
        WorkItem(dataset="assays", entity=f"S{i}", interval=interval, params=params or {})
        for i in range(n)
    ]


def make_limiter(provider: Provider, clock: Clock, seed: int = 0) -> ProviderLimiter:
    return ProviderLimiter(
        provider.name, provider.capabilities.rate_limit, clock, random.Random(seed)
    )


class Collector:
    """`on_outcome` callback that remembers what it was handed."""

    def __init__(self) -> None:
        self.seen: list[FetchOutcome] = []

    async def __call__(self, outcome: FetchOutcome) -> None:
        self.seen.append(outcome)


async def run(
    provider: Provider, items: list[WorkItem], limiter: ProviderLimiter, got: Collector
) -> list[FetchOutcome]:
    return await run_items(provider, ASSAYS, items, limiter, got)


async def test_batches_follow_max_batch(
    provider: FakeAssayProvider | FakeBulkAssayProvider, clock: FakeClock
) -> None:
    got = Collector()
    outcomes = await run(provider, make_items(7), make_limiter(provider, clock), got)
    expected_calls = 7 if provider.capabilities.max_batch == 1 else 2
    assert len(provider.calls) == expected_calls
    assert sorted(len(c) for c in provider.calls) == ([1] * 7 if expected_calls == 7 else [2, 5])
    assert [o.item.entity for o in outcomes] == [f"S{i}" for i in range(7)]
    assert all(o.kind == "ok" for o in outcomes)
    assert len(got.seen) == 7


async def test_params_never_share_a_batch(
    provider: FakeAssayProvider | FakeBulkAssayProvider, clock: FakeClock
) -> None:
    items = make_items(3, {"adj": "1"}) + make_items(3, {"adj": "0"})
    await run(provider, items, make_limiter(provider, clock), Collector())
    for call in provider.calls:
        assert len({tuple(sorted(i.params.items())) for i in call}) == 1
    assert sum(len(c) for c in provider.calls) == 6


async def test_concurrency_never_exceeds_policy(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    set_policy(provider, concurrency=2, per_second=None)
    state = {"now": 0, "peak": 0}
    lock = threading.Lock()
    original = provider.fetch

    def slow_fetch(dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.02)
        with lock:
            state["now"] -= 1
        return original(dataset, items)

    provider.fetch = slow_fetch  # type: ignore[method-assign]
    await run(provider, make_items(8), make_limiter(provider, clock), Collector())
    assert state["peak"] == 2


async def test_pacing_spaces_starts(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    set_policy(provider, concurrency=3, per_second=1.0, burst=1)
    starts: list[datetime] = []
    limiter = make_limiter(provider, clock)
    granted = limiter.slot

    @asynccontextmanager
    async def timed_slot() -> AsyncIterator[None]:
        async with granted():
            starts.append(clock.now())  # the moment the limiter lets a call start
            yield

    limiter.slot = timed_slot  # type: ignore[method-assign]
    await run(provider, make_items(3), limiter, Collector())
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(starts)]
    assert len(starts) == 3
    assert all(g >= 1.0 for g in gaps)


async def test_rate_limit_pauses_whole_provider_then_succeeds(
    provider: FakeAssayProvider | FakeBulkAssayProvider, clock: FakeClock
) -> None:
    set_policy(provider, per_second=None, concurrency=3)
    provider.script["S0"] = ["rate_limited"]
    limiter = make_limiter(provider, clock, seed=7)
    outcomes = await run(provider, make_items(4), limiter, Collector())
    expected = 30.0 * (1 + 0.1 * random.Random(7).random())
    assert clock.sleeps == [pytest.approx(expected)]
    assert all(o.kind == "ok" for o in outcomes)


async def test_global_failure_after_consecutive_episodes(
    provider: FakeAssayProvider | FakeBulkAssayProvider, clock: FakeClock
) -> None:
    set_policy(provider, per_second=None, jitter=0.0)
    provider.script["S0"] = ["rate_limited"] * 10
    with pytest.raises(GlobalFailure, match=f"{provider.name}: rate limited 4 times in a row"):
        await run(provider, make_items(1), make_limiter(provider, clock), Collector())
    assert clock.sleeps == [30.0, 60.0, 120.0]


async def test_unreachable_threshold_raises_global_failure(
    provider: FakeAssayProvider | FakeBulkAssayProvider, clock: FakeClock
) -> None:
    set_policy(provider, per_second=None, max_unreachable=3)
    provider.script["S0"] = ["unreachable"] * 10
    with pytest.raises(GlobalFailure, match="unreachable"):
        await run(provider, make_items(1), make_limiter(provider, clock), Collector())
    assert len(provider.calls) == 4
    assert clock.sleeps == [30.0] * 3  # one backoff before each re-queue


async def test_ok_resets_counters(clock: FakeClock) -> None:
    policy = RateLimitPolicy(max_unreachable=2, max_rate_limit_episodes=1, jitter=0.0)
    limiter = ProviderLimiter("p", policy, clock, random.Random(0))
    for _ in range(3):
        await limiter.report("unreachable")
        await limiter.report("unreachable")
        await limiter.report("ok")
        await limiter.report("rate_limited")
        clock.advance(1000)
        await limiter.report("empty")
    with pytest.raises(GlobalFailure):
        for _ in range(3):
            await limiter.report("unreachable")


async def test_error_does_not_reset_or_advance_counters(clock: FakeClock) -> None:
    policy = RateLimitPolicy(max_unreachable=2)
    limiter = ProviderLimiter("p", policy, clock, random.Random(0))
    await limiter.report("unreachable")
    await limiter.report("error")
    await limiter.report("unreachable")
    with pytest.raises(GlobalFailure):
        await limiter.report("unreachable")


async def test_concurrent_rate_limits_are_one_episode(clock: FakeClock) -> None:
    policy = RateLimitPolicy(max_rate_limit_episodes=1, jitter=0.0)
    limiter = ProviderLimiter("p", policy, clock, random.Random(0))
    await limiter.report("rate_limited")
    await limiter.report("rate_limited")  # still paused: same episode, no GlobalFailure


@pytest.mark.parametrize(
    ("script", "kind", "calls"),
    [
        (["error", "error", "error"], "error", 3),
        (["error", "ok"], "ok", 2),
    ],
)
async def test_error_retried_then_final(
    provider: FakeAssayProvider | FakeBulkAssayProvider,
    clock: FakeClock,
    script: list[OutcomeKind],
    kind: str,
    calls: int,
) -> None:
    set_policy(provider, per_second=None)
    provider.script["S0"] = list(script)
    got = Collector()
    outcomes = await run(provider, make_items(1), make_limiter(provider, clock), got)
    assert [o.kind for o in outcomes] == [kind]
    assert len(provider.calls) == calls
    assert clock.sleeps == [30.0] * (calls - 1)
    assert [o.kind for o in got.seen] == [kind]


async def test_outcomes_delivered_before_abort(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    set_policy(provider, per_second=None, concurrency=1, max_unreachable=0)
    provider.script["S2"] = ["unreachable"]
    got = Collector()
    with pytest.raises(GlobalFailure):
        await run(provider, make_items(3), make_limiter(provider, clock), got)
    assert [o.item.entity for o in got.seen] == ["S0", "S1"]


async def test_outcomes_delivered_before_abort_within_one_batch(clock: FakeClock) -> None:
    provider = FakeBulkAssayProvider()
    set_policy(provider, per_second=None, max_unreachable=0)
    provider.script["S2"] = ["unreachable"]
    got = Collector()
    with pytest.raises(GlobalFailure):
        await run(provider, make_items(3), make_limiter(provider, clock), got)
    assert [o.item.entity for o in got.seen] == ["S0", "S1"]


async def test_outcomes_after_failing_one_in_batch_still_delivered(clock: FakeClock) -> None:
    provider = FakeBulkAssayProvider()
    set_policy(provider, per_second=None, max_unreachable=0)
    provider.script["S1"] = ["unreachable"]
    got = Collector()
    with pytest.raises(GlobalFailure):
        await run(provider, make_items(3), make_limiter(provider, clock), got)
    assert [o.item.entity for o in got.seen] == ["S0", "S2"]


async def test_one_sleep_per_round_with_unreachable_and_error(clock: FakeClock) -> None:
    provider = FakeBulkAssayProvider()
    set_policy(provider, per_second=None)
    provider.script["S0"] = ["unreachable"]
    provider.script["S1"] = ["error"]
    outcomes = await run(provider, make_items(2), make_limiter(provider, clock), Collector())
    assert [o.kind for o in outcomes] == ["ok", "ok"]
    assert clock.sleeps == [30.0]


async def test_fetch_raising_global_failure_propagates(clock: FakeClock) -> None:
    provider = FakeAssayProvider()

    def boom(dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        raise GlobalFailure("auth invalid")

    provider.fetch = boom  # type: ignore[method-assign]
    with pytest.raises(GlobalFailure, match="auth invalid"):
        await run(provider, make_items(2), make_limiter(provider, clock), Collector())


async def test_wrong_outcome_count_raises(
    provider: FakeAssayProvider | FakeBulkAssayProvider, clock: FakeClock
) -> None:
    original = provider.fetch

    def drop_one(dataset: Dataset, items: list[WorkItem]) -> list[FetchOutcome]:
        return original(dataset, items)[:-1]

    provider.fetch = drop_one  # type: ignore[method-assign]
    with pytest.raises(ValueError, match=provider.name):
        await run(provider, make_items(2), make_limiter(provider, clock), Collector())


# -- circuit breakers (core.md, Source store) ----------------------------------------------------


def serial(provider: Provider, **policy: object) -> None:
    """One call at a time, no pacing or retries: outcomes complete in input order."""
    set_policy(provider, concurrency=1, per_second=None, max_error_retries=0, **policy)


async def test_consecutive_errors_across_entities_raise_global_failure(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    serial(provider, max_consecutive_errors=3)
    for i in range(5):
        provider.script[f"S{i}"] = ["error"]
    got = Collector()
    with pytest.raises(GlobalFailure, match=r"fake.*3.*scripted error"):
        await run(provider, make_items(5), make_limiter(provider, clock), got)
    assert [o.item.entity for o in got.seen] == ["S0", "S1", "S2"]  # handed over, as before


async def test_retries_of_one_entity_count_once(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    set_policy(provider, per_second=None, max_error_retries=2, max_consecutive_errors=2)
    provider.script["S0"] = ["error", "error", "error"]  # three error answers, one entity
    outcomes = await run(provider, make_items(1), make_limiter(provider, clock), Collector())
    assert [o.kind for o in outcomes] == ["error"]


async def test_ok_resets_error_streak(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    serial(provider, max_consecutive_errors=3)
    for i in (0, 1, 3, 4):
        provider.script[f"S{i}"] = ["error"]
    outcomes = await run(provider, make_items(5), make_limiter(provider, clock), Collector())
    assert [o.kind for o in outcomes] == ["error", "error", "ok", "error", "error"]


async def test_consecutive_empty_trips_global_failure(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    serial(provider, max_consecutive_empty=3)
    provider.unknown = {f"S{i}" for i in range(5)}
    got, tripped = Collector(), Collector()

    async def on_tripped(held: list[FetchOutcome]) -> None:
        tripped.seen.extend(held)

    with pytest.raises(GlobalFailure, match=r"fake.*3.*empty"):
        await run_items(
            provider, ASSAYS, make_items(5), make_limiter(provider, clock), got, on_tripped=on_tripped
        )
    assert got.seen == []  # held back, never handed to on_outcome
    assert [o.item.entity for o in tripped.seen] == ["S0", "S1", "S2"]


async def test_empty_streak_below_threshold_is_handed_over(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    serial(provider, max_consecutive_empty=3)
    provider.unknown = {"S0", "S1", "S3"}  # streak of two, an ok, then one more
    got = Collector()
    outcomes = await run(provider, make_items(4), make_limiter(provider, clock), got)
    assert [o.kind for o in outcomes] == ["empty", "empty", "ok", "empty"]
    assert sorted(o.item.entity for o in got.seen) == ["S0", "S1", "S2", "S3"]


async def test_breakers_off_by_default(clock: FakeClock) -> None:
    provider = FakeAssayProvider()
    serial(provider)
    provider.unknown = {f"S{i}" for i in range(10)}
    for i in range(10, 20):
        provider.script[f"S{i}"] = ["error"]
    got = Collector()
    outcomes = await run(provider, make_items(20), make_limiter(provider, clock), got)
    assert len(outcomes) == len(got.seen) == 20
