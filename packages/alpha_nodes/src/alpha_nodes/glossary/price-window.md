---
id: price-window
name: Price window
abbreviations: []
aliases: []
kind: count
fields: [PriceWindow]
implemented_by: [alpha_nodes.metrics.PriceWindow]
related: [period-window]
status: draft
sources: []
summary: "The trading bars a price metric was computed from: how many, which dates, and how many were flagged suspect."
category: window
---

## Definition

Every price metric result reports the daily bars it used: `bars`, the first and last bar dates (`start`, `end`), `suspect_bars` and the `currency` the bars trade in.

## How we calculate it

Windows count bars (trading sessions), not calendar days: one month is 21 bars, one year 252, three years 756. `bars` is what was actually used, so a short history gives fewer bars than the nominal window. Bars labelled `suspect` by data-quality checks are used, and counted in `suspect_bars`; rejected bars never reach a calc.

## Why it matters

It tells the reader how much history stands behind a number, and whether any of it is doubtful.

## Shortcomings and pitfalls

Bars are trading sessions on the venue's own calendar, so a window covers different calendar spans in different markets. Counting suspect bars says nothing about how wrong they are.

## Similar terms

See [period window](period-window.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

`bars` is how many trading sessions the number used; fewer than the nominal window means short history. `start` and `end` are the first and last bar dates. `suspect_bars` counts bars flagged unreliable by data checks. `currency` is the trading currency of the bars, which prefixes price values. A metric is null when the history is too short.
