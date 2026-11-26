---
id: common-equity
name: Common equity
abbreviations: []
aliases: []
kind: money
fields: [FundamentalsSchema.common_equity]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [return-on-equity, debt-to-equity, total-equity]
status: draft
sources: []
summary: Equity attributable to the parent's common shareholders at period end.
category: statement
---

## Definition

The part of equity belonging to the parent company's ordinary shareholders (excluding minorities).

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Buybacks and write-downs shrink it, which inflates ROE and leverage ratios; it can be negative.

## Similar terms

See [return on equity](return-on-equity.md), [debt to equity](debt-to-equity.md), [total equity](total-equity.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Equity attributable to the parent's common shareholders at period end, in the reporting currency's major unit. The denominator of ROE and debt to equity.
