---
id: debt-to-equity
name: Debt to equity
abbreviations: [D/E]
aliases: []
kind: ratio
fields: [BalanceSheetResult.debt_to_equity]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.BalanceSheet, alpha_nodes.kernels.fundamentals.safe_ratio]
related: [interest-cover, net-debt, total-debt, common-equity]
status: draft
sources: []
summary: Total debt as a multiple of common equity at the latest period.
category: leverage
---

## Definition

How much the company has borrowed for each unit of shareholders' equity.

## How we calculate it

$\text{total debt} / \text{common equity}$ at the latest complete point (see [period window](period-window.md)); null when equity is not positive. Total debt includes finance leases and excludes operating lease liabilities.

## Why it matters

Low leverage means the business can survive bad years without lenders.

## Shortcomings and pitfalls

Buybacks shrink equity and inflate the ratio; negative equity makes it undefined; operating leases are left out.

## Similar terms

See [interest cover](interest-cover.md), [net debt](net-debt.md), [total debt](total-debt.md), [common equity](common-equity.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Total debt over common equity at the latest complete period; 0.5 means debt is half of equity. Excludes operating leases. Null when equity is not positive. May come from an older period, see field_periods.
