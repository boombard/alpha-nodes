"""Named bar-count conventions shared by kernels and calc nodes.

Windows count bars (sessions), not calendar days; see documentation/design/finance.md,
Pinned conventions.
"""

BARS_PER_MONTH = 21
BARS_PER_YEAR = 252  # also the annualisation factor, for every venue

FILING_LAG_DAYS = 90  # a period with no filing date counts as known 90 days after period_end
MAX_ANNUAL_PERIODS = 10  # fundamentals windows take at most the last 10 known annual periods
MAX_STALE_PERIODS = 2  # a latest-point field may come from at most 2 periods before the latest
