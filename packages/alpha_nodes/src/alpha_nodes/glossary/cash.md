---
id: cash
name: Cash
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.cash]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [net-debt, total-debt]
status: draft
sources: []
summary: Cash and equivalents at period end.
category: statement
---

## Definition

Cash and short-term liquid holdings at the period end.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Some cash is needed to run the business or is held abroad, so it is not all available to repay debt.

## Similar terms

See [net debt](net-debt.md), [total debt](total-debt.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Cash and cash equivalents at period end. Null when unreported.
