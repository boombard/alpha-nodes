---
id: total-liabilities
name: Total liabilities
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.total_liabilities]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [total-assets, total-equity, total-debt]
status: draft
sources: []
summary: Everything the company owes, at period end.
category: statement
---

## Definition

The sum of all liabilities on the balance sheet at the period end.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

It mixes debt with non-interest-bearing items like payables.

## Similar terms

See [total assets](total-assets.md), [total equity](total-equity.md), [total debt](total-debt.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Total liabilities at period end, in the reporting currency's major unit. When a filer does not tag it, it is derived as assets less equity or left null.
