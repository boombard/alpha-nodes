---
id: trend-close
name: Trend close
abbreviations: []
aliases: []
kind: money
fields: [TrendResult.close]
implemented_by: [alpha_nodes.nodes.price_calcs.Trend]
related: [moving-average, pct-above-ma]
status: draft
sources: []
summary: The latest split-adjusted close used by the trend metrics.
category: price
---

## Definition

The last close of the trend window, in the major unit of the trading currency.

## How we calculate it

The last close of the window, as the provider gives it (split-adjusted, dividends not added back). Null when history is too short for the trend.

## Why it matters

It is the price the moving average is compared with.

## Shortcomings and pitfalls

It is a single day's close, so one noisy day moves it.

## Similar terms

See [200-bar moving average](moving-average.md), [close vs moving average](pct-above-ma.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Latest close of the trend window, split-adjusted. The price that the moving average is compared with. Null when history is too short.
