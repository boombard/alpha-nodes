---
id: pe
name: Price to earnings
abbreviations: [P/E, PE]
aliases: []
kind: ratio
fields: [ValuationResult.pe, ValuationChangeResult.pe_now, ValuationChangeResult.pe_then]
implemented_by: [alpha_nodes.nodes.valuation_calcs.Valuation, alpha_nodes.valuation.valuation_on, alpha_nodes.nodes.valuation_calcs.ValuationChange]
related: [earnings-yield, pe-change, market-cap]
status: draft
sources: []
summary: "Market capitalisation divided by net income: how many years of profit the price equals."
category: valuation
---

## Definition

The price paid per unit of annual profit.

## How we calculate it

$\text{market cap} / \text{net income}$ with the latest known annual period; null when net income is not positive. The `_now` and `_then` fields are the same at the two dates of a valuation change.

## Why it matters

It is the most common shorthand for how expensive a stock is.

## Shortcomings and pitfalls

A low P/E can mean a cheap stock or a business in decline; earnings are annual, not trailing, and cyclical peaks flatter it.

## Similar terms

See [earnings yield](earnings-yield.md), [p/e change](pe-change.md), [market capitalisation](market-cap.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Market cap divided by latest annual net income; 15 means the price is 15 years of earnings. Null when earnings are not positive. The _now and _then fields give the same at two dates. A low value is not automatically cheap.
