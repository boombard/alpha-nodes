from datetime import date

import pytest
from lensgraph.charts import LineChart
from lensgraph.store.files import FileBlobStore
from lensgraph.store.memory import InMemoryBlobStore
from pydantic import ValidationError

X = [date(2024, 1, 1), date(2024, 1, 2)]


def test_line_chart_series_length_mismatch_rejected():
    with pytest.raises(ValidationError, match="close"):
        LineChart(title="t", x=X, series={"close": [1.0]})


def test_line_chart_needs_a_series():
    with pytest.raises(ValidationError, match="series"):
        LineChart(title="t", x=X, series={})


@pytest.mark.parametrize("kind", ["file", "memory"])
def test_line_chart_roundtrips_blob_stores(kind, tmp_path):
    store = FileBlobStore(tmp_path) if kind == "file" else InMemoryBlobStore()
    chart = LineChart(title="t", x=X, series={"close": [1.0, None]}, y_label="USD")
    back = store.get(store.put(chart))
    assert back == chart
    assert back.series["close"][1] is None
