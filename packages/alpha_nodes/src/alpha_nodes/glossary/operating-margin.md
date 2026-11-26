---
id: operating-margin
name: Operating margin
abbreviations: []
aliases: []
kind: ratio
fields: [ProfitabilityResult.op_margin_mean, ProfitabilityResult.op_margin_std]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.Profitability, alpha_nodes.kernels.fundamentals.safe_ratio, alpha_nodes.kernels.fundamentals.mean_std]
related: [return-on-equity, op-margin-change-1y, operating-income, revenue]
status: draft
sources: []
summary: Operating income as a share of revenue, with its mean and spread across the window.
category: profitability
---

## Definition

The share of each unit of revenue left after operating costs, before interest and tax, per annual period.

## How we calculate it

Per period $\text{operating income} / \text{revenue}$, null when revenue is not positive. `op_margin_mean` is the mean and `op_margin_std` the sample standard deviation (needs at least 3 periods).

## Why it matters

A high, stable margin suggests pricing power and cost discipline.

## Shortcomings and pitfalls

Margins differ greatly between industries and are not comparable across them; banks have no operating income, so it is null for them.

## Similar terms

See [return on equity](return-on-equity.md), [operating margin change, 1 year](op-margin-change-1y.md), [operating income](operating-income.md), [revenue](revenue.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Operating income over revenue per annual period; 0.20 means 20%. Fields give the mean and standard deviation across the window. Compare with the company's own history, not across industries. Null when operating income is not reported (for example banks).
