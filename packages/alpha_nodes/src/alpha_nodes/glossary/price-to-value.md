---
id: price-to-value
name: Price to value
abbreviations: []
aliases: []
kind: ratio
fields: [ValuationResult.price_to_value]
implemented_by: []
related: [value-range, market-cap]
status: draft
sources: []
summary: Market capitalisation divided by the midpoint of the intrinsic-value band.
category: valuation
---

## Definition

How the market price compares with our crude value estimate.

## How we calculate it

$\text{market cap} / \tfrac{1}{2}(\text{value low} + \text{value high})$; null when the band is null.

## Why it matters

A value below 1 means the market values the company below the band's midpoint.

## Shortcomings and pitfalls

The band is crude, so treat it as direction, not precision.

## Similar terms

See [intrinsic-value band](value-range.md), [market capitalisation](market-cap.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Market cap divided by the midpoint of the value band; below 1 means priced under the midpoint, above 1 over it. Null when the band is null. Inherits the band's crude no-growth assumptions.
