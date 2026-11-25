"""Provider scheduler: batching, one shared limiter per provider, pause and give-up rules.

The core knows a provider only through what it declares (`ProviderCapabilities`); this
module turns that declaration into behaviour. See documentation/design/core.md, Source
store (the Provider bullets: declared capabilities, core scheduling). Deciding *what* to
fetch is the gap-filler's job and persisting outcomes is the store's; this module only
runs work items and hands each final outcome to a callback the moment it exists.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from ..types import GlobalFailure
from .base import Clock, Provider
from .models import Dataset, FetchOutcome, OutcomeKind, RateLimitPolicy, WorkItem

OnOutcome = Callable[[FetchOutcome], Awaitable[None]]
OnTripped = Callable[[list[FetchOutcome]], Awaitable[None]]


class _Held(BaseModel):
    """A withheld `empty` outcome with the callbacks of the call that fetched it.

    The limiter is shared by every `ensure` call on a provider, so whichever call ends or trips
    the streak must not hand another call's outcome to its own callbacks (core.md, Source store,
    Circuit breakers).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    outcome: FetchOutcome
    on_outcome: OnOutcome
    on_tripped: OnTripped | None = None


class ProviderLimiter:
    """One per provider per store: concurrency, token-bucket pacing (per_second, burst), provider-wide pause.

    Also counts consecutive rate-limit episodes and unreachable outcomes and raises
    `GlobalFailure` past the policy's thresholds (see core.md, Source store).
    asyncio primitives are created lazily on first use, so the limiter binds to the loop that uses it.

    Args:
        provider: provider name, used in failure messages.
        policy: the provider's declared `RateLimitPolicy`.
        clock: time source for pauses and pacing (a `FakeClock` in tests).
        rng: source of backoff jitter; seed it for reproducible pauses.
    """

    def __init__(
        self,
        provider: str,
        policy: RateLimitPolicy,
        clock: Clock,
        rng: random.Random | None = None,
    ) -> None:
        self.provider = provider
        self.policy = policy
        self.clock = clock
        self._rng = rng or random.Random()
        self._semaphore: asyncio.Semaphore | None = None
        self._pace_lock: asyncio.Lock | None = None
        self._tokens = float(policy.burst)
        self._refilled_at: datetime | None = None
        self._paused_until: datetime | None = None
        self._episodes = 0  # consecutive rate-limit episodes
        self._unreachable = 0  # consecutive unreachable outcomes
        self._error_entities: set[str] = set()  # entities in the open error streak
        self._empty_entities: set[str] = set()  # entities in the open empty streak (`_held`)
        self._held: list[_Held] = []  # open empty streak, withheld from on_outcome

    async def settle(
        self,
        outcome: FetchOutcome,
        on_outcome: OnOutcome,
        on_tripped: OnTripped | None = None,
    ) -> None:
        """Hand one *final* outcome over and apply the entity-level circuit breakers.

        Unlike `report` (every provider answer, retries included) this sees each entity once.
        Streaks count distinct entities: several items of one entity (one per gap) count once.
        `max_consecutive_errors`: reaching it after the outcome was handed over raises
        `GlobalFailure`. `max_consecutive_empty`: `empty` outcomes are withheld while the streak
        is open and handed over when a non-empty outcome breaks it (or by `flush`); reaching the
        threshold instead drops them (via `on_tripped`, so the store can log them uncached) and
        raises `GlobalFailure`. `ok` resets both streaks, `empty` the error streak, `error`
        the empty streak. Both breakers are off while their policy field is None.

        The streak is provider-wide, but each withheld `empty` keeps the `on_outcome` and
        `on_tripped` of the call that fetched it and is handed over through those, whichever call
        ends the streak.
        """
        kind = outcome.kind
        entity = outcome.item.entity
        if kind == "empty":
            self._error_entities.clear()
            limit = self.policy.max_consecutive_empty
            if limit is None:
                await on_outcome(outcome)
                return
            self._held.append(_Held(outcome=outcome, on_outcome=on_outcome, on_tripped=on_tripped))
            self._empty_entities.add(entity)
            if len(self._empty_entities) >= limit:
                await self.log_tripped(self.take_held())
                raise GlobalFailure(
                    f"{self.provider}: {limit} entities in a row answered empty "
                    "(provider incident or throttling?); nothing cached for them"
                )
            return
        await self.flush()
        await on_outcome(outcome)
        if kind == "ok":
            self._error_entities.clear()
        elif kind == "error":
            self._error_entities.add(entity)
            limit = self.policy.max_consecutive_errors
            if limit is not None and len(self._error_entities) >= limit:
                raise GlobalFailure(
                    f"{self.provider}: {len(self._error_entities)} entities in a row ended in error "
                    f"(last: {outcome.message or 'error'})"
                )

    async def flush(self) -> None:
        """Hand over the withheld `empty` outcomes, each to its own call's `on_outcome`: the streak ended below its threshold."""
        for held in self.take_held():
            await held.on_outcome(held.outcome)

    def take_held(self, owner: OnOutcome | None = None) -> list[_Held]:
        """Remove and return withheld `empty` outcomes: all of them, or only `owner`'s.

        Without `owner` the empty streak ends. With it (a failing call taking back its own
        entries) other calls' entries stay held for their own flush or trip, and the streak keeps
        the entities they cover.
        """
        if owner is None:
            taken, self._held = self._held, []
        else:
            taken = [h for h in self._held if h.on_outcome == owner]
            self._held = [h for h in self._held if h.on_outcome != owner]
        self._empty_entities = {h.outcome.item.entity for h in self._held}
        return taken

    async def log_tripped(self, held: list[_Held]) -> None:
        """Hand dropped `empty` outcomes to their own call's `on_tripped` (grouped per call; None skips)."""
        groups: list[tuple[OnTripped, list[FetchOutcome]]] = []
        for entry in held:
            if entry.on_tripped is None:
                continue
            for callback, outcomes in groups:
                if callback == entry.on_tripped:
                    outcomes.append(entry.outcome)
                    break
            else:
                groups.append((entry.on_tripped, [entry.outcome]))
        for callback, outcomes in groups:
            await callback(outcomes)

    def slot(self) -> AbstractAsyncContextManager[None]:
        """Context manager that waits for a pause to end, a concurrency slot and a pacing token."""
        return self._slot()

    @asynccontextmanager
    async def _slot(self):
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.policy.concurrency)
            self._pace_lock = asyncio.Lock()
        async with self._semaphore:
            while True:
                await self._wait_for_pause()
                await self._take_token()
                if self._pause_remaining() <= 0:  # a pause may have begun while pacing
                    break
            yield

    def _pause_remaining(self) -> float:
        if self._paused_until is None:
            return 0.0
        return (self._paused_until - self.clock.now()).total_seconds()

    async def _wait_for_pause(self) -> None:
        while (remaining := self._pause_remaining()) > 0:
            await self.clock.sleep(remaining)

    async def _take_token(self) -> None:
        """Block until a pacing token is available (no-op without `per_second`)."""
        rate = self.policy.per_second
        if rate is None:
            return
        assert self._pace_lock is not None
        async with self._pace_lock:
            while True:
                now = self.clock.now()
                if self._refilled_at is not None:
                    elapsed = (now - self._refilled_at).total_seconds()
                    self._tokens = min(float(self.policy.burst), self._tokens + elapsed * rate)
                self._refilled_at = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                await self.clock.sleep((1.0 - self._tokens) / rate)

    async def report(self, kind: OutcomeKind) -> None:
        """Feed one outcome kind into the counters; pauses on rate limits, raises `GlobalFailure` past thresholds.

        `rate_limited` starts a new episode unless the provider is already paused (outcomes of
        calls that were in flight together are one episode). `ok` and `empty` reset both counters;
        `error` touches neither.
        """
        if kind in ("ok", "empty"):
            self._episodes = 0
            self._unreachable = 0
        elif kind == "unreachable":
            self._unreachable += 1
            if self._unreachable > self.policy.max_unreachable:
                raise GlobalFailure(
                    f"{self.provider}: unreachable {self._unreachable} times in a row"
                )
        elif kind == "rate_limited" and self._pause_remaining() <= 0:
            self._episodes += 1
            if self._episodes > self.policy.max_rate_limit_episodes:
                raise GlobalFailure(
                    f"{self.provider}: rate limited {self._episodes} times in a row"
                )
            schedule = self.policy.backoff_s
            base = schedule[min(self._episodes - 1, len(schedule) - 1)]
            seconds = base * (1 + self.policy.jitter * self._rng.random())
            self._paused_until = self.clock.now() + timedelta(seconds=seconds)


def _batches(items: Sequence[WorkItem], max_batch: int) -> list[list[tuple[int, WorkItem]]]:
    """Group `(input index, item)` pairs into batches of at most `max_batch`, never mixing params."""
    by_params: dict[tuple[tuple[str, str], ...], list[tuple[int, WorkItem]]] = {}
    for index, item in enumerate(items):
        by_params.setdefault(tuple(sorted(item.params.items())), []).append((index, item))
    return [
        group[start : start + max_batch]
        for group in by_params.values()
        for start in range(0, len(group), max_batch)
    ]


async def _run_batch(
    provider: Provider,
    dataset: Dataset,
    batch: list[tuple[int, WorkItem]],
    limiter: ProviderLimiter,
    on_outcome: OnOutcome,
    results: dict[int, FetchOutcome],
    on_tripped: OnTripped | None = None,
) -> None:
    """Fetch one batch until every item has a final outcome, re-queuing what isn't final."""
    policy = provider.capabilities.rate_limit
    error_retries: dict[int, int] = {}
    pending = batch
    while pending:
        async with limiter.slot():
            outcomes = await asyncio.to_thread(provider.fetch, dataset, [i for _, i in pending])
        if len(outcomes) != len(pending):
            raise ValueError(
                f"{provider.name}: fetch returned {len(outcomes)} outcomes for {len(pending)} items"
            )
        # Classify the whole batch and hand over every final outcome first, so a GlobalFailure
        # raised while reporting an earlier outcome cannot strand later final ones.
        requeue: list[tuple[int, WorkItem]] = []
        needs_delay = False  # an unreachable or error item is being retried this round
        failure: GlobalFailure | None = None  # first breaker trip; raised after the round
        for (index, item), outcome in zip(pending, outcomes, strict=True):
            if outcome.kind == "rate_limited":
                requeue.append((index, item))
            elif outcome.kind == "unreachable":
                requeue.append((index, item))
                needs_delay = True
            elif outcome.kind == "error" and error_retries.get(index, 0) < policy.max_error_retries:
                error_retries[index] = error_retries.get(index, 0) + 1
                requeue.append((index, item))
                needs_delay = True
            else:
                results[index] = outcome
                if failure is not None and outcome.kind == "empty":
                    if on_tripped is not None:  # after a trip nothing more is cached for empties
                        await on_tripped([outcome])
                    continue
                try:
                    await limiter.settle(outcome, on_outcome, on_tripped)
                except GlobalFailure as exc:
                    failure = failure or exc
        if failure is not None:
            raise failure
        for outcome in outcomes:
            await limiter.report(outcome.kind)
        if needs_delay:
            await limiter.clock.sleep(policy.backoff_s[0])
        pending = requeue


async def run_items(
    provider: Provider,
    dataset: Dataset,
    items: Sequence[WorkItem],
    limiter: ProviderLimiter,
    on_outcome: OnOutcome,
    on_tripped: OnTripped | None = None,
) -> list[FetchOutcome]:
    """Run work items through `provider` and return the final outcomes in input order.

    Items are batched up to the provider's declared `max_batch` (equal `params` only) and every
    batch runs under `limiter`. `rate_limited` and `unreachable` outcomes are re-queued;
    `error` is retried up to `max_error_retries` times; a round that re-queues any `unreachable` or
    `error` item first sleeps `backoff_s[0]` on the clock (once per round), so a short blip can't burn
    through `max_unreachable` instantly; `ok` and `empty` are final. Each final
    outcome is awaited into `on_outcome` as soon as it exists, so the store can persist it
    before other batches finish. `GlobalFailure` cancels outstanding batches and propagates;
    outcomes already handed over stay handed over.

    Raises:
        GlobalFailure: from the limiter's thresholds and circuit breakers or from `provider.fetch`.
        ValueError: if the provider returns the wrong number of outcomes.
    """
    results: dict[int, FetchOutcome] = {}
    batches = _batches(items, provider.capabilities.max_batch)
    tasks = [
        asyncio.create_task(
            _run_batch(provider, dataset, b, limiter, on_outcome, results, on_tripped)
        )
        for b in batches
    ]
    try:
        await asyncio.gather(*tasks)
        await limiter.flush()
    except BaseException as exc:
        # This call's open empties: asked, so logged, but never cached. Other calls' stay held.
        held = limiter.take_held(owner=on_outcome)
        if held and not isinstance(exc, asyncio.CancelledError):
            await limiter.log_tripped(held)  # each to its own call; skipped on cancellation
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return [results[i] for i in range(len(items))]
