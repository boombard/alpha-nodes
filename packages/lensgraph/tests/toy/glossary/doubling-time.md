---
id: doubling-time
name: Doubling time
abbreviations: []
aliases: []
kind: duration
fields: [GrowthResult.doubling_hours]
implemented_by: [toy.nodes.GrowthRate]
related: [growth-rate]
status: verified
sources: [lab-handbook]
summary: Hours for the biomass to double.
category: growth
---

## Definition

Time for the culture to double.

## How we calculate it

Computed as $\ln 2 / r$ for growth rate $r$.

## Why it matters

Short doubling times mean quick turnaround.

## Shortcomings and pitfalls

Only valid inside the exponential phase.

## Similar terms

See [growth rate](growth-rate.md).

## Sources

Lab handbook, ch. 3.

## Prompt note

Hours to double. Smaller means faster growth.
