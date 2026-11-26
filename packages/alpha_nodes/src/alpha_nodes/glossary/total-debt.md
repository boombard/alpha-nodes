---
id: total-debt
name: Total debt
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.total_debt]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [debt-to-equity, net-debt, cash]
status: draft
sources: []
summary: Interest-bearing borrowings at period end.
category: statement
---

## Definition

Short- and long-term borrowings, including finance leases, outstanding at the period end.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Different filers tag debt differently, so a partial composition is possible; check the row's suspect flag.

## Similar terms

See [debt to equity](debt-to-equity.md), [net debt](net-debt.md), [cash](cash.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Interest-bearing debt at period end, in the reporting currency's major unit, including finance leases; operating lease liabilities are excluded. Composed from several tags, so it can be partial.
