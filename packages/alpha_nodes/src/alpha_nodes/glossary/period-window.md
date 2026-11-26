---
id: period-window
name: Period window
abbreviations: []
aliases: []
kind: count
fields: [PeriodWindow]
implemented_by: [alpha_nodes.metrics.PeriodWindow]
related: [price-window, statement-row]
status: draft
sources: []
summary: "The annual fundamentals periods a metric used: how many, which period ends, currency, suspect count, and fields taken from older periods."
category: window
---

## Definition

Every fundamentals result reports its window: `periods`, `first_period_end`, `last_period_end`, `suspect_periods`, `currency` and `field_periods`. A field that cannot be computed is null, never 0.

## How we calculate it

At most 10 known annual periods are used (a period is known once filed, or 90 days after its period end when the provider has no filing dates). A latest-point field (leverage, coverage, net debt, owner earnings, FCF) takes the newest of the last three periods that hold all of its inputs. When that is older than `last_period_end`, `field_periods` records the field and the `period_end` it came from; only such older fields are listed. The window of a result spans from the oldest row any field used to the latest period.

## Why it matters

It shows how much history a metric rests on and flags stale fields, so a verdict can be less confident when key numbers are old.

## Shortcomings and pitfalls

A field listed in `field_periods` is not wrong, only older, and a ratio is never mixed across periods. A short window makes means and spreads unreliable.

## Similar terms

See [price window](price-window.md), [statement row](statement-row.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

`periods` is how many annual periods were used, between `first_period_end` and `last_period_end`, in `currency` (the reporting currency). `suspect_periods` counts periods flagged unreliable. `field_periods` lists only fields taken from an older period than `last_period_end`, mapped to that period's end: weigh those less, and lower conviction when key fields are stale. A null field means not computable, never zero.
