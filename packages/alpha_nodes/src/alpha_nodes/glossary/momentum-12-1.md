---
id: momentum-12-1
name: 12-1 momentum
abbreviations: [MOM]
aliases: []
kind: ratio
fields: [MomentumResult.total_return]
implemented_by: [alpha_nodes.nodes.price_calcs.Momentum, alpha_nodes.kernels.returns.skip_return]
related: [trend-close, pct-above-ma, total-return-index]
status: draft
sources: []
summary: Total return from twelve months ago to one month ago, skipping the most recent month.
category: price
---

## Definition

The classic cross-sectional momentum signal: how much the stock gained over the past year, leaving out the latest month to avoid short-term reversal.

## How we calculate it

On the total-return index $TR$ (dividends reinvested on their ex-date; closes are already split-adjusted): $TR_{t-21} / TR_{t-252} - 1$ over bars. It needs at least 253 bars, else it is null.

## Why it matters

Stocks that rose over the past year have, on average, tended to keep outperforming for some months.

## Shortcomings and pitfalls

It is a statistical tendency, not a reason by itself to buy; it says nothing about the business and crashes in sharp market reversals.

## Similar terms

See [trend close](trend-close.md), [close vs moving average](pct-above-ma.md).
Also [total-return index](total-return-index.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Total return with dividends reinvested from twelve months ago to one month ago, skipping the latest month; 0.15 means 15%. Null under 253 bars. Context about the price path, not a verdict on the business.
