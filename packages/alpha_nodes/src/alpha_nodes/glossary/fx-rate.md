---
id: fx-rate
name: FX rate to reporting currency
abbreviations: []
aliases: []
kind: ratio
fields: [ValuationResult.fx_rate]
implemented_by: []
related: [valuation-price, market-cap]
status: draft
sources: []
summary: Reporting-currency units per trading-currency unit on the price date.
category: valuation
---

## Definition

The exchange rate used to convert the market price into the currency of the financial statements.

## How we calculate it

Reporting-currency units per one trading-currency unit on `price_date`, from the daily fx dataset; 1 when the two currencies match.

## Why it matters

Market cap and earnings are only comparable in one currency.

## Shortcomings and pitfalls

A stale or missing fx rate makes the conversion wrong, and currency swings move multiples without business change.

## Similar terms

See [valuation price](valuation-price.md), [market capitalisation](market-cap.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Reporting-currency units per trading-currency unit on the price date; 1.0 when the currencies are the same. A conversion factor, not a signal.
