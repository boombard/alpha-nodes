---
id: total-return-index
name: Total-return index
abbreviations: [TR]
aliases: [total return index]
kind: ratio
fields: [TotalReturnSchema.date, TotalReturnSchema.close, TotalReturnSchema.dividends, TotalReturnSchema.tr_index, TotalReturnSchema.suspect]
implemented_by: [alpha_nodes.nodes.price_calcs.TotalReturn, alpha_nodes.kernels.returns.total_return_index]
related: [momentum-12-1, volatility, max-drawdown]
status: draft
sources: []
summary: "A price index that starts at 1 and grows with the close plus reinvested dividends."
category: price
---

## Definition

The value of one unit invested at the first bar, with every dividend reinvested on its ex-date. It is the base series of the price metrics, one row per bar with ascending unique dates.

## How we calculate it

$TR_0 = 1$ and $TR_t = TR_{t-1} \times (\text{close}_t + \text{dividend}_t) / \text{close}_{t-1}$, with the dividend on its ex-date row. `split_ratio` is not applied, because provider closes are already split-adjusted; dividends are assumed to be on the same split basis. `suspect` is true when the source bar was labelled suspect; `close` is the provider's close.

## Why it matters

Price alone understates what a holder earned from a dividend payer; the index makes returns, volatility and drawdown comparable across payers and non-payers.

## Shortcomings and pitfalls

Dividends are assumed reinvested at the ex-date close, with no tax or fees. A payout straddling a split is not directly observed.

## Similar terms

See [12-1 momentum](momentum-12-1.md), [realised volatility](volatility.md), [maximum drawdown](max-drawdown.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Per bar: date, split-adjusted close, dividend paid that day, and an index of total return starting at 1.0 on the first bar (1.2 means a 20% gain with dividends reinvested). Suspect marks a bar flagged unreliable by data checks.
