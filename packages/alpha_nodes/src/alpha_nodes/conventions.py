"""Named bar-count conventions shared by kernels and calc nodes.

Windows count bars (sessions), not calendar days; see documentation/design/finance.md,
Pinned conventions.
"""

BARS_PER_MONTH = 21
BARS_PER_YEAR = 252  # also the annualisation factor, for every venue
