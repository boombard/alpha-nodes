---
id: revenue-cagr-3y
name: Revenue CAGR, 3 years
abbreviations: [CAGR]
aliases: []
kind: growth
fields: [FundamentalTrendResult.revenue_cagr_3y]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.FundamentalTrend, alpha_nodes.kernels.fundamentals.cagr]
related: [revenue-growth-1y, revenue]
status: draft
sources: []
summary: Compound annual revenue growth from about three years earlier to the latest period.
category: growth
---

## Definition

The smoothed yearly growth rate of sales over about three years.

## How we calculate it

$(\text{revenue}_{last} / \text{revenue}_{base})^{1/y} - 1$, with the base the period whose `period_end` is closest to three years earlier (within 6 months, else null) and $y$ the actual years between the two ends. Both ends must be positive.

## Why it matters

It smooths a single good or bad year.

## Shortcomings and pitfalls

Endpoints matter: a recovery from a depressed base flatters it.

## Similar terms

See [revenue growth, 1 year](revenue-growth-1y.md), [revenue](revenue.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Compound annual growth of revenue from about three years before the latest period. Null when no period sits within 6 months of three years back. A depressed base flatters it.
