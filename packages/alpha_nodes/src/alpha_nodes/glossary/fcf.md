---
id: fcf
name: Free cash flow
abbreviations: [FCF]
aliases: [free cash flow to equity (loosely)]
kind: money
fields: [CashGenerationResult.fcf]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.CashGeneration]
related: [fcf-conversion, fcf-growth-1y, owner-earnings, operating-cash-flow, capex]
status: draft
sources: []
summary: Operating cash flow less capital expenditure at the latest period.
category: cash generation
---

## Definition

The cash the business generated after paying for the investment in its assets.

## How we calculate it

$\text{operating cash flow} - \text{capex}$ at the latest complete point (capex is a positive number, cash spent); reporting currency.

## Why it matters

FCF funds dividends, buybacks, debt repayment and acquisitions.

## Shortcomings and pitfalls

It is lumpy year to year, ignores acquisitions, and can be flattered by delaying capex or stretching payables.

## Similar terms

See [fcf conversion](fcf-conversion.md), [fcf growth, 1 year](fcf-growth-1y.md), [owner earnings](owner-earnings.md), [operating cash flow](operating-cash-flow.md), [capital expenditure](capex.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Operating cash flow minus capex at the latest complete period. Negative means the business consumed cash. Lumpy year to year. May come from an older period, see field_periods.
