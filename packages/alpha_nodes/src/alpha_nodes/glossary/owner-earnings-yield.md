---
id: owner-earnings-yield
name: Owner earnings yield
abbreviations: []
aliases: []
kind: ratio
fields: [ValuationResult.owner_earnings_yield]
implemented_by: [alpha_nodes.nodes.valuation_calcs.Valuation, alpha_nodes.valuation.valuation_on]
related: [owner-earnings, earnings-yield, market-cap]
status: draft
sources: []
summary: Owner earnings as a share of market capitalisation.
category: valuation
---

## Definition

The cash-style earnings return on the price paid, using our owner-earnings proxy.

## How we calculate it

$\text{owner earnings} / \text{market cap}$ at the latest known period.

## Why it matters

It compares owner earnings with a required return (the hurdle rate).

## Shortcomings and pitfalls

It inherits the assumptions of [owner earnings](owner-earnings.md), the maintenance-capex proxy above all.

## Similar terms

See [owner earnings](owner-earnings.md), [earnings yield](earnings-yield.md), [market capitalisation](market-cap.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Owner earnings over market cap at the latest known period; 0.08 means 8%. Inherits the maintenance-capex assumption of owner earnings. Negative when owner earnings are negative.
