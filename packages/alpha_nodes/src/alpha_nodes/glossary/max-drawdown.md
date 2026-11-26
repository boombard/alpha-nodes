---
id: max-drawdown
name: Maximum drawdown
abbreviations: [MDD]
aliases: []
kind: ratio
fields: [DrawdownResult.max_drawdown]
implemented_by: [alpha_nodes.nodes.price_calcs.Drawdown, alpha_nodes.kernels.risk.max_drawdown]
related: [drawdown-dates, volatility, total-return-index]
status: draft
sources: []
summary: The largest peak-to-trough fall of the total-return index in the window.
category: price
---

## Definition

The worst loss an investor would have suffered buying at a peak and selling at the following trough.

## How we calculate it

Over the last at most 756 bars of the total-return index: $\min_t (TR_t / \max_{s \le t} TR_s) - 1$, a non-positive fraction. Needs at least 252 bars, else null. 0 when the series never fell.

## Why it matters

It shows the depth of pain in the price history that volatility averages away.

## Shortcomings and pitfalls

It depends on the window chosen and on one episode; it says nothing of how long recovery took.

## Similar terms

See [drawdown peak and trough dates](drawdown-dates.md), [realised volatility](volatility.md).
Also [total-return index](total-return-index.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Largest peak-to-trough fall of total return in the window, a fraction at or below zero; -0.30 means a 30% fall. Zero means it never fell. Null under 252 bars.
