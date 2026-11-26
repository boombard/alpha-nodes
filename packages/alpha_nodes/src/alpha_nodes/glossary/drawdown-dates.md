---
id: drawdown-dates
name: Drawdown peak and trough dates
abbreviations: []
aliases: []
kind: date
fields: [DrawdownResult.peak_date, DrawdownResult.trough_date]
implemented_by: [alpha_nodes.nodes.price_calcs.Drawdown, alpha_nodes.kernels.risk.drawdown_extent]
related: [max-drawdown]
status: draft
sources: []
summary: The dates of the peak and the trough of the maximum drawdown.
category: price
---

## Definition

When the worst fall began (peak) and when it bottomed (trough).

## How we calculate it

The bar dates at the peak and the trough found by `drawdown_extent` on the same window as the maximum drawdown. Null when there was no fall or too little history.

## Why it matters

They place the worst episode in time, so it can be matched with news or the business cycle.

## Shortcomings and pitfalls

They mark one episode only, and the current state may be mid-recovery or mid-fall.

## Similar terms

See [maximum drawdown](max-drawdown.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Dates of the peak and of the trough of the maximum drawdown in the window. Null when the price never fell or history is too short.
