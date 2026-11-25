"""The day finance calcs are evaluated on."""

from datetime import UTC, date, datetime

from lensgraph.node import NodeContext


def reference_day(ctx: NodeContext) -> date:
    """The day a calc is evaluated on: `ctx.as_of`, else the `sources` store clock's today, else today (UTC).

    Using the store's clock keeps replays with a fake clock deterministic. See
    documentation/design/finance.md, Pinned conventions (Known on a date).
    """
    if ctx.as_of is not None:
        return ctx.as_of
    clock = getattr(ctx.services.get("sources"), "clock", None)
    return (clock.now() if clock is not None else datetime.now(UTC)).date()
