---
id: interest-cover
name: Interest cover
abbreviations: []
aliases: []
kind: ratio
fields: [BalanceSheetResult.interest_cover]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.BalanceSheet, alpha_nodes.kernels.fundamentals.safe_ratio]
related: [debt-to-equity, operating-income, interest-expense]
status: draft
sources: []
summary: How many times operating income covers interest expense at the latest period.
category: leverage
---

## Definition

A measure of how comfortably the company can pay the interest on its debt out of operating profit.

## How we calculate it

$\text{operating income} / \text{interest expense}$ at the latest complete point; null when interest expense is missing or not positive.

## Why it matters

Thin cover means a small drop in profit can threaten payments.

## Shortcomings and pitfalls

Interest expense can be missing or netted against interest income by the provider, which flatters or hides the figure.

## Similar terms

See [debt to equity](debt-to-equity.md), [operating income](operating-income.md), [interest expense](interest-expense.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Operating income divided by interest expense at the latest complete period; 8 means operating income covers interest eight times. Null when interest expense is missing or zero (not the same as infinite cover). May come from an older period.
