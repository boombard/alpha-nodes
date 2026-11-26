---
id: net-income
name: Net income
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.net_income]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [return-on-equity, owner-earnings, eps-growth-1y]
status: draft
sources: []
summary: Profit for the year attributable to common shareholders.
category: statement
---

## Definition

The bottom-line profit left for common shareholders after all costs, interest, tax and minority interests.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

It includes one-offs, tax effects and write-downs, so it can mislead about the underlying business.

## Similar terms

See [return on equity](return-on-equity.md), [owner earnings](owner-earnings.md), [eps growth, 1 year](eps-growth-1y.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Net income attributable to common shareholders for the annual period. A loss is negative.
