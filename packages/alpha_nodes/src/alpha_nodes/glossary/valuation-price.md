---
id: valuation-price
name: Valuation price
abbreviations: []
aliases: []
kind: money
fields: [ValuationResult.price_date, ValuationResult.close, ValuationResult.trading_currency]
implemented_by: []
related: [fx-rate, market-cap]
status: draft
sources: []
summary: The latest close, its date and trading currency, which the valuation multiples are computed from.
category: valuation
---

## Definition

The market price used to value the company: the close on `price_date`, in the major unit of `trading_currency`.

## How we calculate it

The last close on or before the valuation day, as given by the provider (split-adjusted). Market cap and multiples are built from it.

## Why it matters

A multiple is only as current as the price it uses.

## Shortcomings and pitfalls

It is level-based, so a stale `price_date` makes every multiple stale.

## Similar terms

See [fx rate to reporting currency](fx-rate.md), [market capitalisation](market-cap.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

The close used for valuation, its date and the currency it trades in (major unit). It is the latest market price, not a target or fair value. Check price_date for staleness.
