---
id: value-range
name: Intrinsic-value band
abbreviations: []
aliases: []
kind: money
fields: [ValuationResult.value_low, ValuationResult.value_high]
implemented_by: [alpha_nodes.nodes.valuation_calcs.Valuation, alpha_nodes.valuation.valuation_on]
related: [owner-earnings, price-to-value]
status: draft
sources: []
summary: "A crude value range: owner earnings capitalised at a high and a low required return."
category: valuation
---

## Definition

A low and a high estimate of what the business is worth if owner earnings stayed flat forever.

## How we calculate it

$\text{owner earnings} / r$ at the hurdle rates $r$ (default 12% gives the low value, 8% the high one); null when owner earnings are not positive. Reporting currency.

## Why it matters

It gives a conservative anchor to compare the market value against.

## Shortcomings and pitfalls

It assumes no growth and a fixed discount rate, and it is only as good as the owner-earnings proxy. A rough band, not a forecast.

## Similar terms

See [owner earnings](owner-earnings.md), [price to value](price-to-value.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

A rough value band in the reporting currency: owner earnings capitalised at the default 12% (low) and 8% (high) required returns. Null when owner earnings are not positive. Assumes no growth; an anchor, not a forecast.
