---
id: roic-pretax
name: Return on invested capital, pre-tax
abbreviations: []
aliases: []
kind: ratio
fields: [CapitalReturnsResult.roic_pretax_mean, CapitalReturnsResult.roic_pretax_min, CapitalReturnsResult.roic_pretax_std]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.CapitalReturns, alpha_nodes.kernels.fundamentals.invested_capital, alpha_nodes.kernels.fundamentals.safe_ratio, alpha_nodes.kernels.fundamentals.mean_std]
related: [incremental-roic, return-on-equity, operating-income, total-debt, total-equity, cash]
status: draft
sources: []
summary: Operating income as a share of invested capital (debt plus equity less cash), with its mean, minimum and spread across the window.
category: profitability
---

## Definition

How much operating profit the business earns on all the capital tied up in it, whoever supplied it. We report the mean, the minimum and the standard deviation across the window.

## How we calculate it

Per period $\text{ROIC}_{pre-tax} = \text{operating income} / (\text{total debt} + \text{total equity} - \text{cash})$, null when invested capital is not positive (those periods are skipped). `roic_pretax_mean` and `roic_pretax_min` are over the valid periods; `roic_pretax_std` is the sample standard deviation and needs at least 3 periods. Null for banks and insurers, which report no operating income.

## Why it matters

High returns on capital that persist, rather than fading back to the average, are one of the measurable signatures of a durable competitive advantage.

## Shortcomings and pitfalls

Pre-tax, because tax expense is not ingested, so it overstates after-tax returns by the tax rate. Goodwill is not adjusted. A high level shows past returns, not that they will last; it is a sign, not proof.

## Similar terms

See [incremental ROIC](incremental-roic.md), [return on equity](return-on-equity.md), [operating income](operating-income.md), [total debt](total-debt.md), [total equity](total-equity.md), [cash](cash.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Pre-tax operating income over invested capital (debt plus equity less cash) per annual period. Fields give mean, minimum and standard deviation across the window (spread needs 3 or more periods). Periods with non-positive capital are skipped. Null for banks and insurers.
