---
id: fcf-growth-1y
name: FCF growth, 1 year
abbreviations: []
aliases: []
kind: growth
fields: [FundamentalTrendResult.fcf_growth_1y]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.FundamentalTrend, alpha_nodes.kernels.fundamentals.growth]
related: [fcf, operating-cash-flow, capex]
status: draft
sources: []
summary: Growth in free cash flow between the latest two annual periods.
category: growth
---

## Definition

How much free cash flow grew in the latest year.

## How we calculate it

The growth rate is $(\text{cur} - \text{prev}) / |\text{prev}|$, null when the earlier value is 0. Applied to $\text{operating cash flow} - \text{capex}$ of the latest two periods; null when they are more than 18 months apart.

## Why it matters

Cash growth is harder to manufacture than profit growth.

## Shortcomings and pitfalls

Free cash flow is lumpy and can be negative, so percentage changes swing widely.

## Similar terms

See [free cash flow](fcf.md), [operating cash flow](operating-cash-flow.md), [capital expenditure](capex.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Growth of free cash flow between the latest two annual periods, relative to the earlier one's size. Lumpy and can swing widely; a negative base makes the sign misleading. Null when periods are more than 18 months apart.
