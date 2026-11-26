---
id: incremental-roic
name: Incremental ROIC, pre-tax
abbreviations: []
aliases: []
kind: ratio
fields: [CapitalReturnsResult.incremental_roic_pretax]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.CapitalReturns, alpha_nodes.kernels.fundamentals.incremental_return]
related: [roic-pretax, operating-income, capex-intensity]
status: draft
sources: []
summary: The extra operating income earned per unit of extra invested capital between a base period and the latest period.
category: profitability
---

## Definition

Whether new capital keeps earning high returns, as opposed to the average return flattering old, already-built assets.

## How we calculate it

$(\text{op income}_{latest} - \text{op income}_{base}) / (\text{capital}_{latest} - \text{capital}_{base})$, using invested capital as in [pre-tax ROIC](roic-pretax.md). The base is the period closest to five years before the latest (within 6 months); failing that, the one closest to three years back. Null when there is no such base or invested capital did not grow.

## Why it matters

A business with a durable advantage can reinvest at high returns; one without sees new capital earn little.

## Shortcomings and pitfalls

Noisy: operating income moves with the cycle between the two end points, and acquisitions add capital and income at once. Two points only, not a trend.

## Similar terms

See [pre-tax ROIC](roic-pretax.md), [operating income](operating-income.md), [capex intensity](capex-intensity.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Rise in operating income over rise in invested capital, latest period against a base about 5 years back (else about 3); 0.20 means 20% pre-tax. Null when no base exists or capital did not grow. Two end points, so cycles distort it.
