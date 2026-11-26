---
id: net-debt
name: Net debt
abbreviations: []
aliases: []
kind: money
fields: [BalanceSheetResult.net_debt]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.BalanceSheet]
related: [debt-to-equity, total-debt, cash]
status: draft
sources: []
summary: Total debt less cash at the latest period, in the reporting currency.
category: leverage
---

## Definition

What the company owes after using its cash to repay debt.

## How we calculate it

$\text{total debt} - \text{cash}$ at the latest complete point, in the reporting currency's major unit. Negative means net cash.

## Why it matters

It is the debt a buyer of the whole business would inherit.

## Shortcomings and pitfalls

Cash may be trapped, needed for operations or held abroad; the figure does not net other liabilities such as leases or pensions.

## Similar terms

See [debt to equity](debt-to-equity.md), [total debt](total-debt.md), [cash](cash.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Total debt minus cash at the latest complete period, in the reporting currency's major unit. Negative means net cash. Not scaled by size, so judge against earnings. May come from an older period, see field_periods.
