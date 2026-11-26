---
id: total-assets
name: Total assets
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.total_assets]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [total-liabilities, total-equity]
status: draft
sources: []
summary: Everything the company owns, at book value, at period end.
category: statement
---

## Definition

The sum of all assets on the balance sheet at the period end.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Book values are historical cost and include goodwill and intangibles of uncertain worth.

## Similar terms

See [total liabilities](total-liabilities.md), [total equity](total-equity.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Total assets at period end, in the reporting currency's major unit. Null when unreported.
