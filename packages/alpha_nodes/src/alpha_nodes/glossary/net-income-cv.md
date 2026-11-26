---
id: net-income-cv
name: Earnings variability
abbreviations: [CV]
aliases: []
kind: ratio
fields: [ProfitabilityResult.net_income_cv]
implemented_by: [alpha_nodes.nodes.fundamental_calcs.Profitability, alpha_nodes.kernels.fundamentals.coefficient_of_variation]
related: [loss-years, net-income]
status: draft
sources: []
summary: "The standard deviation of annual net income divided by its mean: lower means steadier earnings."
category: profitability
---

## Definition

The coefficient of variation of net income across the window, a scale-free measure of how erratic earnings are.

## How we calculate it

$\sigma(\text{net income}) / \overline{\text{net income}}$ over the window's periods; null when the mean is not positive or there are fewer than 3 periods.

## Why it matters

Consistent earning power is easier to value than a volatile profit.

## Shortcomings and pitfalls

With few periods it is noisy, and growth itself raises the spread, so a fast grower can look erratic.

## Similar terms

See [loss years](loss-years.md), [net income](net-income.md).

## Sources

Draft, written from model knowledge; not yet researched.

## Prompt note

Standard deviation of annual net income divided by its mean over the window; 0.3 means the spread is 30% of the mean. Lower is steadier. Null when the mean is not positive or under 3 periods. Growth also raises it.
