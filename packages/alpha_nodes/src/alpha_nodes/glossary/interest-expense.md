---
id: interest-expense
name: Interest expense
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.interest_expense]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [interest-cover, total-debt]
status: draft
sources: []
summary: Interest paid on debt for the year, as a positive cost.
category: statement
---

## Definition

The cost of borrowing recorded in the year.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Some providers net it against interest income, which hides the true borrowing cost.

## Similar terms

See [interest cover](interest-cover.md), [total debt](total-debt.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Interest expense for the annual period; positive means a cost. Null when unreported.
