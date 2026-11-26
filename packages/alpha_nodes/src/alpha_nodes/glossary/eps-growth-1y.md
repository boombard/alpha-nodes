---
id: eps-growth-1y
name: EPS growth, 1 year
abbreviations: []
aliases: []
kind: growth
fields: [FundamentalTrendResult.eps_growth_1y]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.FundamentalTrend, alpha_nodes.kernels.fundamentals.growth]
related: [net-income, shares-diluted]
status: draft
sources: []
summary: Growth in earnings per share between the latest two annual periods.
category: growth
---

## Definition

How much profit per share grew in the latest year.

## How we calculate it

EPS is $\text{net income} / \text{diluted shares}$ (computed by us, never ingested). The growth rate is $(\text{cur} - \text{prev}) / |\text{prev}|$, null when the earlier value is 0. Null when the periods are more than 18 months apart.

## Why it matters

Per-share growth captures both profit growth and dilution or buybacks.

## Shortcomings and pitfalls

Growth off a negative or tiny base is misleading; one-off items distort it.

## Similar terms

See [net income](net-income.md), [diluted shares](shares-diluted.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Growth of earnings per share (net income over weighted diluted shares) between the latest two annual periods. Null when periods are more than 18 months apart. Growth from a loss or a tiny base is misleading.
