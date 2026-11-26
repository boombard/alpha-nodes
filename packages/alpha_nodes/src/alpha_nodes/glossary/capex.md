---
id: capex
name: Capital expenditure
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.capex]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [fcf, owner-earnings, depreciation-amortization]
status: draft
sources: []
summary: Cash spent on property, plant and equipment in the year, as a positive number.
category: statement
---

## Definition

Money spent buying or improving long-lived assets.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

It mixes maintenance and growth spending, and acquisitions are not included.

## Similar terms

See [free cash flow](fcf.md), [owner earnings](owner-earnings.md), [depreciation and amortisation](depreciation-amortization.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Capital expenditure for the annual period; positive means cash spent. Null when unreported.
