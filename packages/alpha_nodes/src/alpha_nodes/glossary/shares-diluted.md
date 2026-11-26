---
id: shares-diluted
name: Diluted shares
abbreviations: []
aliases: []
kind: shares
fields: [FundamentalsSchema.shares_diluted]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema]
related: [shares-outstanding, share-count-cagr, eps-growth-1y]
status: draft
sources: []
summary: Weighted-average share count for the year, including dilutive securities.
category: statement
---

## Definition

The average number of shares during the year if options and convertibles were exercised.

## How we calculate it

An ingested line item of the annual fundamentals frame, in the reporting currency's major unit: provider-neutral, nullable (a missing item is null, never 0), taken from the filing known on the as-of day.

## Why it matters

It is an input to the fundamentals calcs listed under related terms.

## Shortcomings and pitfalls

An average over the year, so it lags the period-end count; unadjusted splits distort history.

## Similar terms

See [shares outstanding](shares-outstanding.md), [share-count trend](share-count-cagr.md), [eps growth, 1 year](eps-growth-1y.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Weighted-average diluted shares for the annual period, as a share count. The denominator of EPS. Null when unreported.
