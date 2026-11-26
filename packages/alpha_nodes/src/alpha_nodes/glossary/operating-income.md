---
id: operating-income
name: Operating income
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.operating_income]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [operating-margin, interest-cover]
status: draft
sources: []
summary: Profit from operations before interest and tax.
category: statement
---

## Definition

Revenue less operating costs, before interest and tax.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

One-off charges are included unless the provider strips them; banks and insurers have no comparable figure.

## Similar terms

See [operating margin](operating-margin.md), [interest cover](interest-cover.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Operating profit for the annual period, in the reporting currency's major unit. Null when the provider reports none (banks); null is not zero.
