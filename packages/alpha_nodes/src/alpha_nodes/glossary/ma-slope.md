---
id: ma-slope
name: Moving-average slope
abbreviations: []
aliases: []
kind: ratio
fields: [TrendResult.ma_slope]
implemented_by: [alpha_nodes.nodes.price_calcs.Trend, alpha_nodes.kernels.rolling.linreg_slope]
related: [moving-average, pct-above-ma]
status: draft
sources: []
summary: The annualised growth rate of the 200-bar moving average, fitted over its last 20 bars.
category: price
---

## Definition

Whether the moving average is itself rising or falling, and how fast.

## How we calculate it

$252 \times$ the regression slope of $\ln \text{MA}_{200}$ over the last 20 bars, so a log growth rate per year. Needs 219 bars, else null.

## Why it matters

A rising average confirms a trend that a price merely above it might not.

## Shortcomings and pitfalls

Log growth is close to, but not exactly, percentage growth for large moves; a short fit window is noisy.

## Similar terms

See [200-bar moving average](moving-average.md), [close vs moving average](pct-above-ma.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Annualised log growth of the 200-bar moving average over its last 20 bars; 0.10 means the average is rising about 10% a year, negative means falling. Null when history is too short.
