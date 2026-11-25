"""Generic chart value types a node may output and a claim may cite.

See documentation/design/core.md, Reporting. A cited chart has kind "chart" in the run view (lineage.py, view/models.py) and is drawn by
the UI's `LineChartView`.
"""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class LineChart(BaseModel):
    """A titled set of line series over shared dates; domain-neutral, safe for blob stores."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    x: list[date]
    series: dict[str, list[float | None]]  # series name -> y values, each as long as `x`
    y_label: str | None = None

    @model_validator(mode="after")
    def _check_series(self) -> Self:
        """Require at least one series and every series to match `x` in length."""
        if not self.series:
            raise ValueError("LineChart needs at least one series")
        bad = sorted(n for n, ys in self.series.items() if len(ys) != len(self.x))
        if bad:
            raise ValueError(f"series {bad} must have the same length as x ({len(self.x)})")
        return self
