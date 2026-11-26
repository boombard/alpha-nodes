---
id: pe-change
name: P/E change
abbreviations: []
aliases: []
kind: ratio
fields: [ValuationChangeResult.pe_change]
implemented_by: [alpha_nodes.nodes.valuation_calcs.ValuationChange]
related: [pe, valuation-dates, earnings-yield]
status: draft
sources: []
summary: The relative change of the P/E ratio between two dates a year apart.
category: valuation
---

## Definition

Whether the market is paying more or less for each unit of earnings than a year ago (re-rating or de-rating).

## How we calculate it

$\text{pe}_{now} / \text{pe}_{then} - 1$, with each P/E computed at its own date from the periods known then. `then` is 252 bars before `now`.

## Why it matters

A price rising faster than earnings shows as a rising P/E: the market's view changed, not just the profit.

## Shortcomings and pitfalls

Needs positive earnings on both dates, and a change in accounting year can drive it.

## Similar terms

See [P/E](pe.md), [valuation comparison dates](valuation-dates.md), [earnings yield](earnings-yield.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Relative change in P/E between now and about a year earlier; positive means re-rating up, negative means de-rating. Null when either P/E is null.
