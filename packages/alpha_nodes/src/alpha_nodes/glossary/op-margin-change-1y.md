---
id: op-margin-change-1y
name: Operating margin change, 1 year
abbreviations: []
aliases: []
kind: ratio
fields: [FundamentalTrendResult.op_margin_change_1y]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.FundamentalTrend]
related: [operating-margin, revenue-growth-1y]
status: draft
sources: []
summary: The change in operating margin between the latest two annual periods, in fraction points.
category: growth
---

## Definition

Whether profitability per unit of sales improved or worsened in the latest year.

## How we calculate it

$\text{margin}_{last} - \text{margin}_{prev}$ (a difference, not a ratio); null when the periods are more than 18 months apart.

## Why it matters

Rising margins on rising sales are the strongest sign of an improving business.

## Shortcomings and pitfalls

A one-off cost or gain in either year moves it.

## Similar terms

See [operating margin](operating-margin.md), [revenue growth, 1 year](revenue-growth-1y.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Latest operating margin minus the previous one; negative means it fell. Null when periods are more than 18 months apart.
