"""Tests for the TA-Lib reference snapshot tooling (TASK-42). Pure parsing/rendering, no network."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_talib_reference.py"
spec = importlib.util.spec_from_file_location("sync_talib_reference", SCRIPT)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

SMA = """---
title: "Simple Moving Average (SMA)"
description: "Simple Moving Average: the unweighted mean of the last N values."
---

## Inputs

- `inReal` — Source series to average

## Outputs

- `outReal` — Simple moving average

## Parameters

| Parameter | Type | Default | Accepted values | Description |
| --- | --- | --- | --- | --- |
| `optInTimePeriod` | integer | 30 | 1–100000 | Number of bars |

Python: `talib.SMA`, see [ta-lib-python](https://ta-lib.github.io/ta-lib-python/func_groups/overlap_studies.html).
"""

MACD = """---
title: "MACD"
description: "Fast minus slow EMA."
---

## Inputs

- `inReal` — Input series

## Outputs

- `outMACD` — line
- `outMACDSignal` — signal

## Parameters

| Parameter | Type | Default | Accepted values | Description |
| --- | --- | --- | --- | --- |
| `optInFastPeriod` | integer | 12 | 2–100000 | Fast |
| `optInSlowPeriod` | integer | 26 | 2–100000 | Slow |
"""

NEWFUNC = """---
title: "Brand New (NEWFUNC)"
description: "Only on TA-Lib main."
---

## Inputs

- `inHigh` — High
- `inLow` — Low
- `inClose` — Close

## Outputs

- `outInteger` — flag

Python: `talib.NEWFUNC`, see [ta-lib-python](https://ta-lib.github.io/ta-lib-python/func_groups/pattern_recognition.html).
"""

WRAPPER_GROUPS = {"Overlap Studies": ["SMA"], "Momentum Indicators": ["MACD"]}


def _functions() -> list:
    return [
        sync.parse_page("sma", SMA),
        sync.parse_page("macd", MACD),
        sync.parse_page("newfunc", NEWFUNC),
    ]


def test_parses_frontmatter_and_params():
    sma = sync.parse_page("sma", SMA)
    assert sma.name == "SMA"
    assert sma.title == "Simple Moving Average (SMA)"
    assert sma.description == "Simple Moving Average: the unweighted mean of the last N values."
    assert sma.inputs == ["real"]
    assert sma.outputs == ["real"]
    assert [(p.name, p.default) for p in sma.params] == [("timePeriod", "30")]
    assert sma.page_group == "Overlap Studies"
    macd = sync.parse_page("macd", MACD)
    assert [(p.name, p.default) for p in macd.params] == [
        ("fastPeriod", "12"),
        ("slowPeriod", "26"),
    ]
    assert macd.page_group is None
    assert sync.parse_page("newfunc", NEWFUNC).params == []


def test_index_marks_functions_missing_from_wrapper():
    index = sync.render_index(_functions(), WRAPPER_GROUPS, "9.9.9")
    assert "in ta-lib-python 9.9.9 |" in index
    rows = {
        line.split("|")[1].strip(): line for line in index.splitlines() if "](functions/" in line
    }
    assert rows["[SMA](functions/sma.md)"].rstrip().endswith("| yes |")
    assert rows["[NEWFUNC](functions/newfunc.md)"].rstrip().endswith("| no |")
    assert "timePeriod=30" in rows["[SMA](functions/sma.md)"]
    assert "high, low, close" in rows["[NEWFUNC](functions/newfunc.md)"]


def test_index_groups_are_from_wrapper_or_page():
    index = sync.render_index(_functions(), WRAPPER_GROUPS, "9.9.9")
    sections = {}
    current = ""
    for line in index.splitlines():
        if line.startswith("### "):
            current = line[4:]
        elif "](functions/" in line:
            sections[line.split("|")[1].strip().split("]")[0][1:]] = current
    assert sections == {
        "SMA": "Overlap Studies",
        "MACD": "Momentum Indicators",
        "NEWFUNC": "Pattern Recognition",  # not in wrapper: group from the page link
    }


def test_group_is_not_invented_when_unknown():
    page = sync.parse_page(
        "zzz",
        NEWFUNC.replace("pattern_recognition", "")
        .replace("Python: ", "")
        .replace("`talib.NEWFUNC`", ""),
    )
    index = sync.render_index([page], {}, "9.9.9")
    assert "### Ungrouped" in index


def test_dev_talib_matches_numpy_sma():
    import talib

    close = pd.Series(np.arange(1.0, 21.0) ** 1.5)
    expected = close.rolling(5).mean()
    np.testing.assert_allclose(talib.SMA(close.to_numpy(), timeperiod=5), np.asarray(expected))
