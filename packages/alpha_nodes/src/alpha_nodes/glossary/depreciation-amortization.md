---
id: depreciation-amortization
name: Depreciation and amortisation
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.depreciation_amortization]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [owner-earnings, capex]
status: draft
sources: []
summary: The non-cash charge spreading the cost of assets over their lives.
category: statement
---

## Definition

The yearly write-off of the cost of tangible and intangible assets.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Acquisition accounting can inflate amortisation; it is only a rough guide to real wear on assets.

## Similar terms

See [owner earnings](owner-earnings.md), [capital expenditure](capex.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Depreciation and amortisation for the annual period; a non-cash charge. Null when unreported.
