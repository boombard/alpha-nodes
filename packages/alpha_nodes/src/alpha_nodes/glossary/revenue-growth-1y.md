---
id: revenue-growth-1y
name: Revenue growth, 1 year
abbreviations: []
aliases: []
kind: growth
fields: [FundamentalTrendResult.revenue_growth_1y]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.FundamentalTrend, alpha_nodes.kernels.fundamentals.growth]
related: [revenue-cagr-3y, revenue]
status: draft
sources: []
summary: Revenue growth between the latest two annual periods.
category: growth
---

## Definition

How much sales grew in the latest year.

## How we calculate it

The growth rate is $(\text{cur} - \text{prev}) / |\text{prev}|$, null when the earlier value is 0. Compares the latest two periods; null when their `period_end`s are more than 18 months apart.

## Why it matters

Growth in sales is the top of every other growth story.

## Shortcomings and pitfalls

Acquisitions, currency moves and a 53-week year can all move it without organic change.

## Similar terms

See [revenue cagr, 3 years](revenue-cagr-3y.md), [revenue](revenue.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Latest annual revenue against the previous one; 0.08 means 8% growth. Null when the two periods are more than 18 months apart. Acquisitions and currency moves can drive it.
