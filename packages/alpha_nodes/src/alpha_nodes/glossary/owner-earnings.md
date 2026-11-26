---
id: owner-earnings
name: Owner earnings
abbreviations: []
aliases: []
kind: money
fields: [CashGenerationResult.owner_earnings]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.CashGeneration, alpha_nodes.kernels.fundamentals.owner_earnings]
related: [fcf, fcf-conversion, owner-earnings-yield, net-income]
status: draft
sources: []
summary: "Net income plus depreciation less estimated maintenance capital spending: the cash a business could pay out while staying as it is."
category: cash generation
---

## Definition

A proxy for the cash earnings left to the owners after the investment needed to sustain the business.

## How we calculate it

$\text{net income} + \text{D\&A} - \min(\text{capex}, \text{D\&A})$ at the latest complete point: maintenance capex is proxied by depreciation and amortisation, capped at actual capex.

## Why it matters

It is closer to economic earnings than reported profit when depreciation differs from real reinvestment needs.

## Shortcomings and pitfalls

Maintenance capex is an assumption, not a reported number; growth capex is not separated; working-capital changes are ignored.

## Similar terms

See [free cash flow](fcf.md), [fcf conversion](fcf-conversion.md), [owner earnings yield](owner-earnings-yield.md), [net income](net-income.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Proxy for owner earnings in the reporting currency: net income plus D&A less maintenance capex, with maintenance capex estimated as D&A capped at actual capex. An estimate, not reported. May come from an older period, see field_periods.
