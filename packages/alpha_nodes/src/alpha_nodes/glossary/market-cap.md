---
id: market-cap
name: Market capitalisation
abbreviations: [mkt cap]
aliases: []
kind: money
fields: [ValuationResult.market_cap]
implemented_by: [alpha_nodes.nodes.valuation_calcs.Valuation, alpha_nodes.valuation.valuation_on]
related: [earnings-yield, owner-earnings-yield, shares-outstanding, fx-rate]
status: draft
sources: []
summary: Close times shares outstanding, converted to the reporting currency.
category: valuation
---

## Definition

The market's value of all the company's shares.

## How we calculate it

$\text{close} \times \text{shares outstanding}$ of the latest known period, in the trading currency, then converted to the reporting currency by the fx rate on that day.

## Why it matters

It is the price of the business that earnings and cash are compared with.

## Shortcomings and pitfalls

Period-end share counts lag current counts; companies with several share classes may have no count at all, leaving it null.

## Similar terms

See [earnings yield](earnings-yield.md), [owner earnings yield](owner-earnings-yield.md), [shares outstanding](shares-outstanding.md), [fx rate to reporting currency](fx-rate.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Close times period-end shares outstanding, converted to the reporting currency's major unit. Shares come from the latest known period, so it can lag buybacks and issuance. Null when shares are unavailable.
