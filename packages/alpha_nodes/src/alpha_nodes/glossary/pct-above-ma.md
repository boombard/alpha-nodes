---
id: pct-above-ma
name: Close vs moving average
abbreviations: []
aliases: []
kind: ratio
fields: [TrendResult.pct_above_ma]
implemented_by: [alpha_nodes.nodes.price_calcs.Trend]
related: [moving-average, ma-slope]
status: draft
sources: []
summary: How far the latest close sits above (positive) or below (negative) its 200-bar moving average.
category: price
---

## Definition

The distance of the close from the moving average, as a fraction of the average.

## How we calculate it

$\text{close}_{t} / \text{MA}_{t} - 1$ at the last bar.

## Why it matters

It measures how stretched the price is relative to its trend.

## Shortcomings and pitfalls

A large value can mean strength or an overextended move; it does not say which.

## Similar terms

See [200-bar moving average](moving-average.md), [moving-average slope](ma-slope.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Fraction of the moving average that the latest close is above it; 0.10 means 10% above, negative means below. A stretched value can mean strength or overextension. Null when history is too short.
