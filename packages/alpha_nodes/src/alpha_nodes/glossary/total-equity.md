---
id: total-equity
name: Total equity
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.total_equity]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [common-equity, total-assets]
status: draft
sources: []
summary: Net assets at period end, including minority interest.
category: statement
---

## Definition

Total assets less total liabilities, including the share belonging to minority owners of subsidiaries.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Includes minorities and can be depressed or negative after large buybacks.

## Similar terms

See [common equity](common-equity.md), [total assets](total-assets.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Total equity at period end including minority interest. Compare with common equity, which excludes minorities.
