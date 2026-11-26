---
id: loss-years
name: Loss years
abbreviations: []
aliases: []
kind: count
fields: [ProfitabilityResult.loss_years]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.Profitability]
related: [net-income-cv, net-income]
status: draft
sources: []
summary: How many annual periods in the window had negative net income.
category: profitability
---

## Definition

A count of years in which the company lost money.

## How we calculate it

The number of periods in the window with net income below zero; null when no net income is available.

## Why it matters

Earnings consistency is a quality signal; any loss year is worth explaining.

## Shortcomings and pitfalls

A single one-off write-down can create a loss year in an otherwise sound business; the count ignores size.

## Similar terms

See [earnings variability](net-income-cv.md), [net income](net-income.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Number of annual periods in the window with negative net income (a whole number). Zero means none lost money. Null when net income is unavailable. One large write-down can explain a loss year.
