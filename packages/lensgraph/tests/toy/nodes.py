"""Toy "strains" domain nodes (deliberately non-finance).

A small fetch -> transform -> calc graph over microbial strains that exercises the core the way
a finance domain would (prices -> cleaned prices -> momentum).
"""

from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pandera.pandas as pa
from lensgraph.node import CalcNode, FetchNode, NodeContext, TransformNode
from lensgraph.types import ContractViolation
from lensgraph.units import NUMBER
from pydantic import BaseModel, ConfigDict

from .unit_models import HOURS


class ToxNote(BaseModel):
    """A citable text snippet; stands in for a document an AI lens would cite."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    text: str


class AssaySchema(pa.DataFrameModel):
    """Contract for cleaned assay data: non-negative time, positive optical density."""

    time_h: float = pa.Field(ge=0, metadata={"unit": HOURS})
    od600: float = pa.Field(gt=0, metadata={"unit": NUMBER})


class ReferencePanel(FetchNode):
    """Shared-scope fetch: data common to all candidates (like a benchmark index)."""

    name: ClassVar[str] = "reference_panel"
    scope: ClassVar = "shared"
    output: ClassVar[Any] = pd.DataFrame

    def run(self, ctx: NodeContext) -> pd.DataFrame:
        return ctx.services["assays"].reference()


class AssayRaw(FetchNode):
    """Per-candidate fetch of raw assay readings (like raw price history)."""

    name: ClassVar[str] = "assay_raw"
    output: ClassVar[Any] = pd.DataFrame

    def run(self, ctx: NodeContext) -> pd.DataFrame:
        assert ctx.candidate is not None
        return ctx.services["assays"].assays(ctx.candidate.id)


class AssayClean(TransformNode):
    """Cleans raw assays. `required_columns` is a config-tweakable input contract."""

    name: ClassVar[str] = "assay_clean"
    inputs: ClassVar[dict[str, str]] = {"raw": "assay_raw"}
    output: ClassVar[Any] = AssaySchema

    required_columns: list[str] = ["time_h", "od600"]  # noqa: RUF012  # columns raw must have

    def check_inputs(self, **inputs: Any) -> None:
        missing = [c for c in self.required_columns if c not in inputs["raw"].columns]
        if missing:
            raise ContractViolation(f"{self.name}: raw is missing columns {missing}")

    def run(self, ctx: NodeContext, raw: pd.DataFrame) -> pd.DataFrame:
        return raw.dropna().reset_index(drop=True)


class GrowthRate(CalcNode):
    """Log-linear growth rate over the last `window` readings; the toy "scored number"."""

    name: ClassVar[str] = "growth_rate"
    inputs: ClassVar[dict[str, str]] = {"assay": "assay_clean", "reference": "reference_panel"}
    output: ClassVar[Any] = float

    window: int = 5  # number of trailing readings used in the fit

    def run(self, ctx: NodeContext, assay: pd.DataFrame, reference: pd.DataFrame) -> float:
        tail = assay.tail(self.window)
        slope = np.polyfit(tail["time_h"], np.log(tail["od600"]), 1)[0]
        return float(slope)


class ToxNotes(FetchNode):
    """Per-candidate fetch of text notes (the input an AI lens would reason over)."""

    name: ClassVar[str] = "tox_notes"
    output: ClassVar[Any] = list

    def run(self, ctx: NodeContext) -> list[ToxNote]:
        assert ctx.candidate is not None
        return ctx.services["assays"].tox_notes(ctx.candidate.id)
