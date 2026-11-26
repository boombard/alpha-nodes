---
id: share-count-cagr
name: Share-count trend
abbreviations: []
aliases: []
kind: growth
fields: [CashGenerationResult.share_count_cagr]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.CashGeneration, alpha_nodes.kernels.fundamentals.cagr]
related: [shares-diluted]
status: draft
sources: []
summary: The compound annual change in diluted shares from the first to the last period of the window.
category: cash generation
---

## Definition

How fast the number of shares has been growing (dilution) or shrinking (buybacks).

## How we calculate it

$(\text{shares}_{last} / \text{shares}_{first})^{1/y} - 1$ on weighted-average diluted shares, with $y$ the years between the two `period_end`s. Needs at least 2 periods.

## Why it matters

Dilution shares the same profit among more owners; buybacks do the opposite.

## Shortcomings and pitfalls

Splits not adjusted by the provider show up as huge changes; stock-based pay dilutes quietly.

## Similar terms

See [diluted shares](shares-diluted.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Compound annual change in diluted share count across the window; 0.02 means 2% more shares a year (dilution), negative means buybacks. Needs 2 or more periods. An unadjusted split can distort it.
