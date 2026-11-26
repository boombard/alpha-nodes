---
id: statement-row
name: Statement row
abbreviations: []
aliases: []
kind: code
fields: [FundamentalsSchema.period_type, FundamentalsSchema.period_end, FundamentalsSchema.filed_at, FundamentalsSchema.currency, AnnualFundamentalsSchema.suspect]
implemented_by: [alpha_nodes.datasets.FundamentalsSchema, alpha_nodes.statements.AnnualFundamentalsSchema]
related: [period-window, revenue]
status: draft
sources: []
summary: "The metadata of one annual statement row: type, period end, filing date, reporting currency and the suspect flag."
category: statement
---

## Definition

Each row of the annual fundamentals frame is one fiscal year: `period_type` (annual), `period_end` (fiscal year end), `filed_at` (filing date), `currency` (reporting currency) and `suspect`.

## How we calculate it

`annual_fundamentals` keeps, per `period_end`, the latest filing known on the as-of day and sorts ascending. `filed_at` is null when the provider has no filing dates; then a period counts as known 90 days after `period_end`. `suspect` marks rows that data checks doubted (for example assets not matching liabilities plus equity).

## Why it matters

They say which year each number belongs to, when it was knowable and in what currency.

## Shortcomings and pitfalls

A restatement is a later filing for the same period; fiscal years end at different dates across companies, so rows are not calendar-aligned.

## Similar terms

See [period window](period-window.md), [revenue](revenue.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

One row per annual period, ascending. period_end is the fiscal year end; filed_at is when it was filed (null where the provider has no filing dates); currency is the reporting currency of the money columns; suspect true means data checks doubted the row.
