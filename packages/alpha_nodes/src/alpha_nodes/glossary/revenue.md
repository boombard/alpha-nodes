---
id: revenue
name: Revenue
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.revenue]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [operating-margin, revenue-growth-1y]
status: draft
sources: []
summary: Total sales for the fiscal year.
category: statement
---

## Definition

Total revenue of the fiscal year, including all operating revenue lines the provider counts as revenue.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Companies and providers define the top line differently (net or gross of some items), so cross-company comparisons need care.

## Similar terms

See [operating margin](operating-margin.md), [revenue growth, 1 year](revenue-growth-1y.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Total sales for the annual period, in the reporting currency's major unit. For some filers it includes leasing and finance income. Null when unavailable.
