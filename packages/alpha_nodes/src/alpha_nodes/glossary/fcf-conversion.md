---
id: fcf-conversion
name: FCF conversion
abbreviations: []
aliases: []
kind: ratio
fields: [CashGenerationResult.fcf_conversion]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.CashGeneration, alpha_nodes.kernels.fundamentals.sum_ratio]
related: [fcf, owner-earnings, net-income]
status: draft
sources: []
summary: Free cash flow summed over the window as a share of summed net income.
category: cash generation
---

## Definition

How much of reported profit turned into free cash over the window.

## How we calculate it

$\sum \text{FCF} / \sum \text{net income}$ over the periods holding all inputs; null when the summed net income is not positive.

## Why it matters

Profit that keeps turning into cash is more trustworthy than profit that does not.

## Shortcomings and pitfalls

A growing business reinvests, so conversion below 1 is not always a problem; one-off items distort a short window.

## Similar terms

See [free cash flow](fcf.md), [owner earnings](owner-earnings.md), [net income](net-income.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Summed free cash flow divided by summed net income over the window; 1 means free cash matches earnings. Null when summed net income is not positive. A growing business may legitimately be below 1.
