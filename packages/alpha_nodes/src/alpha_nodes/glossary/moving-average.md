---
id: moving-average
name: 200-bar moving average
abbreviations: [MA]
aliases: [200-day moving average, SMA 200]
kind: money
fields: [TrendResult.ma]
implemented_by: [alpha_nodes.nodes.price_calcs.Trend, alpha_nodes.kernels.rolling.sma]
related: [trend-close, pct-above-ma, ma-slope]
status: draft
sources: []
summary: The simple average of the last 200 closes.
category: price
---

## Definition

A smoothed price level over about ten months of trading.

## How we calculate it

$\text{SMA}_{200}$ of the split-adjusted close, taken at the last bar. Price, not the total-return index, by convention. Needs 219 bars for the trend metrics, else null.

## Why it matters

Price above a long moving average is read as an uptrend and below it as a downtrend.

## Shortcomings and pitfalls

It lags the price, and it gives false signals in sideways markets.

## Similar terms

See [trend close](trend-close.md), [close vs moving average](pct-above-ma.md), [moving-average slope](ma-slope.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Simple average of the last 200 split-adjusted closes. A slow trend reference. Null when history is too short.
