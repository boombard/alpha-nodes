---
id: op-margin-floor
name: Operating margin floor
abbreviations: []
aliases: []
kind: ratio
fields: [CapitalReturnsResult.op_margin_min]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.CapitalReturns, alpha_nodes.kernels.fundamentals.safe_ratio]
related: [operating-margin, operating-income, revenue]
status: draft
sources: []
summary: The worst annual operating margin in the window.
category: profitability
---

## Definition

How profitable the business was in its worst year in the window.

## How we calculate it

The minimum over the window of $\text{operating income} / \text{revenue}$, skipping periods with non-positive revenue. Null when no period has both figures, for example banks and insurers.

## Why it matters

Pricing power shows in bad years: a business with an advantage keeps its margin when demand is weak or costs rise.

## Shortcomings and pitfalls

The window is a few years and may hold no real downturn; one-off charges can set the minimum.

## Similar terms

See [operating margin](operating-margin.md), [operating income](operating-income.md), [revenue](revenue.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Lowest annual operating margin across the window; 0.08 means the worst year still earned 8%, negative means an operating loss. Null when no period has operating income and revenue. The window may hold no real downturn.
