"""Toy result models and calc nodes for the unit tests: annotated, unannotated and money-style fields."""

from typing import Annotated, Any, ClassVar

import pandera.pandas as pa
from lensgraph.node import CalcNode, NodeContext
from lensgraph.units import FRACTION, MULTIPLE, Unit
from pydantic import BaseModel

HOURS = Unit(id="hours", style="number", suffix=" h")
VOLUME = Unit(id="volume", style="compact", prefix_field="vessel")  # a domain unit: prefixed by a sibling field


class Culture(BaseModel):
    """A strain's culture metrics: every numeric field declares its unit; bool and text need none."""

    yield_frac: Annotated[float | None, FRACTION] = None
    doubling: Annotated[float | None, HOURS] = None
    fold: Annotated[float, MULTIPLE] = 1.0
    volume: Annotated[float, VOLUME] = 0.0
    vessel: str = "L"
    stable: bool = True


class BareCulture(BaseModel):
    """Like `Culture` but one numeric field has no unit (must fail a plan that feeds a lens)."""

    yield_frac: Annotated[float, FRACTION] = 0.0
    doubling: float = 0.0
    stable: bool = True


class CultureFrame(pa.DataFrameModel):
    """Frame contract with one unit column (`ret`) and one unitless text column."""

    ret: float = pa.Field(metadata={"unit": FRACTION})
    label: str


class CultureNode(CalcNode):
    """Produces a `Culture`."""

    name: ClassVar[str] = "culture"
    output: ClassVar[Any] = Culture

    def run(self, ctx: NodeContext) -> Culture:
        return Culture(yield_frac=0.153, doubling=3.5, fold=2.0, volume=12_300_000, vessel="L")


class BareCultureNode(CalcNode):
    """Produces a `BareCulture` under the same node name `culture`."""

    name: ClassVar[str] = "culture"
    output: ClassVar[Any] = BareCulture

    def run(self, ctx: NodeContext) -> BareCulture:
        return BareCulture(yield_frac=0.1, doubling=2.0)
