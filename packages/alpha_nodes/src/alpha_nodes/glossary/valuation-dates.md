---
id: valuation-dates
name: Valuation comparison dates
abbreviations: []
aliases: []
kind: date
fields: [ValuationChangeResult.date_now, ValuationChangeResult.date_then]
implemented_by: []
related: [pe-change]
status: draft
sources: []
summary: The two dates compared in a valuation change.
category: valuation
---

## Definition

The later (`date_now`) and earlier (`date_then`) days at which the multiples were computed.

## How we calculate it

`date_now` is the as-of day; `date_then` is 252 bars earlier. Each side uses only the financial periods known on its own day.

## Why it matters

They show how far apart the comparison is.

## Shortcomings and pitfalls

Fundamentals are annual, so the two dates may share the same latest period, in which case only price moved.

## Similar terms

See [p/e change](pe-change.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

The later and earlier dates compared in the valuation change; the earlier one is about a year before. Each date uses only periods known on that day. If both use the same period, only the price moved.
