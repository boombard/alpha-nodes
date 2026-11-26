---
id: shares-outstanding
name: Shares outstanding
abbreviations: []
aliases: []
kind: shares
fields: [FundamentalsSchema.shares_outstanding]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [shares-diluted, market-cap]
status: draft
sources: []
summary: Shares in issue at the period end.
category: statement
---

## Definition

The number of shares held by investors at the period end.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

Point-in-time and can lag buybacks and issuance since the period end.

## Similar terms

See [diluted shares](shares-diluted.md), [market capitalisation](market-cap.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Shares outstanding at period end, as a share count. Used for market cap. Null when a company has several share classes with no single count.
