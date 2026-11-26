---
id: return-on-equity
name: Return on equity
abbreviations: [ROE]
aliases: []
kind: ratio
fields: [ProfitabilityResult.roe_mean, ProfitabilityResult.roe_min, ProfitabilityResult.roe_std]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.Profitability, alpha_nodes.kernels.fundamentals.safe_ratio, alpha_nodes.kernels.fundamentals.mean_std]
related: [operating-margin, debt-to-equity, net-income, common-equity]
status: draft
sources: []
summary: Net income to common shareholders as a share of common equity, with its mean, minimum and spread across the window.
category: profitability
---

## Definition

How much profit the business earns on shareholders' money, per annual period. We report the mean, the minimum and the standard deviation across the window.

## How we calculate it

Per period $\text{ROE} = \text{net income} / \text{common equity}$, null when equity is not positive (those periods are skipped). `roe_mean` and `roe_min` are over the valid periods, `roe_std` is the sample standard deviation and needs at least 3 periods.

## Why it matters

A high and steady ROE with little debt is the mark of a business that compounds shareholders' capital.

## Shortcomings and pitfalls

Leverage and buybacks raise ROE without improving the business; small or negative equity makes it meaningless or undefined.

## Similar terms

See [operating margin](operating-margin.md), [debt to equity](debt-to-equity.md), [net income](net-income.md), [common equity](common-equity.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Net income to common over common equity for each annual period. Fields give the mean, minimum and standard deviation across the window (spread needs 3 or more periods). Periods with non-positive equity are skipped. Read with debt_to_equity: leverage inflates ROE.
