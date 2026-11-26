---
id: growth-rate
name: Growth rate
abbreviations: [GR]
aliases: []
kind: ratio
fields: [GrowthResult.rate]
implemented_by: [toy.nodes.GrowthRate]
related: [doubling-time]
status: draft
sources: []
summary: Fractional increase in biomass per hour.
category: growth
---

## Definition

How fast a culture's biomass increases per hour.

## How we calculate it

Slope of $\ln(\text{OD})$ against time over the exponential phase.

## Why it matters

Faster growth shortens production runs.

## Shortcomings and pitfalls

Noisy readings in the lag phase inflate or deflate the slope.

## Similar terms

See [doubling time](doubling-time.md).

## Sources

Draft; none yet.

## Prompt note

A per-hour fractional growth. Larger means faster; it is not a yield.
