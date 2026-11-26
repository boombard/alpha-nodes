---
id: earnings-yield
name: Earnings yield
abbreviations: []
aliases: []
kind: ratio
fields: [ValuationResult.earnings_yield, ValuationChangeResult.earnings_yield_now, ValuationChangeResult.earnings_yield_then]
implemented_by: [alpha_nodes.nodes.valuation_calcs.Valuation, alpha_nodes.valuation.valuation_on, alpha_nodes.nodes.valuation_calcs.ValuationChange]
related: [pe, owner-earnings-yield, market-cap, net-income]
status: draft
sources: []
summary: "Net income as a share of market capitalisation: the inverse of the P/E ratio."
category: valuation
---

## Definition

The yearly profit you get per unit of price paid, expressed as a percentage-like fraction.

## How we calculate it

$\text{net income} / \text{market cap}$ using the latest known annual period; the `_now` and `_then` fields are the same at the two dates of a [valuation change](pe-change.md), each with the periods known on its own day.

## Why it matters

It can be compared directly with bond yields and hurdle rates.

## Shortcomings and pitfalls

It uses the last annual, not trailing, profit; negative when the company lost money.

## Similar terms

See [P/E](pe.md), [owner earnings yield](owner-earnings-yield.md), [market capitalisation](market-cap.md), [net income](net-income.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Latest annual net income over market cap; 0.05 means 5%. The _now and _then fields are the same measure at the two comparison dates. Annual, not trailing-twelve-month. Negative when earnings were negative.
