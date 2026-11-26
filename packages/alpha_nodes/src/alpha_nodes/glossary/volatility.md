---
id: volatility
name: Realised volatility
abbreviations: [vol]
aliases: []
kind: ratio
fields: [VolatilityResult.annualised]
implemented_by: [alpha_nodes.nodes.price_calcs.Volatility, alpha_nodes.kernels.risk.realised_volatility]
related: [max-drawdown, total-return-index]
status: draft
sources: []
summary: The annualised standard deviation of daily returns over the last year.
category: price
---

## Definition

How much the price has swung day to day, scaled to a year.

## How we calculate it

Standard deviation (sample, $ddof = 1$) of daily log total returns over the last 252 returns, times $\sqrt{252}$. Needs at least 63 returns, else null.

## Why it matters

It is the usual measure of how risky the price path has been.

## Shortcomings and pitfalls

It treats up and down moves alike and looks only backwards; calm periods understate later risk.

## Similar terms

See [maximum drawdown](max-drawdown.md).
Also [total-return index](total-return-index.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Annualised standard deviation of daily log total returns over about the last year; 0.25 means 25%. Not directional: high means large swings either way. Null under 63 returns.
