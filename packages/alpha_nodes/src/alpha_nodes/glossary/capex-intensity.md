---
id: capex-intensity
name: Capex intensity
abbreviations: []
aliases: []
kind: ratio
fields: [CapitalReturnsResult.capex_to_revenue_mean, CapitalReturnsResult.capex_to_da_mean]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.CapitalReturns, alpha_nodes.kernels.fundamentals.safe_ratio]
related: [capex, depreciation-amortization, revenue, incremental-roic]
status: draft
sources: []
summary: Mean capital expenditure as a share of revenue, and as a multiple of depreciation and amortisation, across the window.
category: profitability
---

## Definition

How much a business must keep spending on assets to sustain and grow its sales.

## How we calculate it

Per period $\text{capex} / \text{revenue}$ and $\text{capex} / \text{D\&A}$, null where the denominator is not positive; the fields are the means over valid periods.

## Why it matters

A low reinvestment need leaves more of the profit free for owners. Capex above depreciation (a ratio over 1) points to growth spending beyond maintenance.

## Shortcomings and pitfalls

Capex is lumpy year to year, and depreciation is an accounting estimate, so the multiple of D&A is only a rough guide to maintenance versus growth.

## Similar terms

See [capital expenditure](capex.md), [depreciation and amortisation](depreciation-amortization.md), [revenue](revenue.md), [incremental ROIC](incremental-roic.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Mean annual capex over revenue, and mean capex over depreciation and amortisation (above 1 means spending beyond maintenance). Periods with a non-positive denominator are skipped. Capex is lumpy.
