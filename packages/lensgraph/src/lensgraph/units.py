"""Units: declared once on a field, formatted everywhere a number is shown.

A `Unit` is pure data attached to a field of an output contract (`Annotated[float, FRACTION]` on
a pydantic model, `pa.Field(metadata={"unit": FRACTION})` on a frame column). `format_value` is
the only formatter: AI evidence (context.py), deterministic claim text (deterministic.py) and
the run view all go through it. Values themselves stay plain floats. Domain-free: a domain
defines its own units as plain `Unit` values. See documentation/design/core.md, Units.
"""

import math
import typing
from collections.abc import Mapping
from types import UnionType
from typing import Any, Literal

import pandas as pd
import pandera.pandas as pa
from pydantic import BaseModel, ConfigDict

from .graph import GraphError


class UnitError(GraphError):
    """A numeric field reaching a lens has no declared unit (raised at plan build)."""


class _SchemaHook:
    """Lets a `Unit` instance sit in `Annotated[...]` metadata without becoming the field's schema.

    Pydantic asks metadata objects that define `__get_pydantic_core_schema__` for the field's
    schema, which would make `Annotated[float, FRACTION]` validate as a `Unit`. On an instance this
    passes the field's own schema through; on the class (where `Unit` is itself a field type, e.g.
    in `Provenance.cite_units`) it is the normal model schema.
    """

    def __get__(self, obj: Any, owner: type) -> Any:
        if obj is None:
            return lambda source, handler: BaseModel.__get_pydantic_core_schema__.__func__(  # type: ignore[attr-defined]
                owner, source, handler
            )
        return lambda source, handler: handler(source)


class Unit(BaseModel):
    """How a number is shown: pure data, so it serialises into provenance and needs no domain code.

    Args:
        id: stable label, e.g. "fraction"; shown in run-view headers.
        style: `percent` multiplies by 100, `multiple` is a ratio, `number` plain, `integer`
            exact, `compact` uses k/m/bn/tn.
        suffix: appended after the number, e.g. "/yr" or " bars".
        prefix_field: sibling field (or frame column) whose value prefixes the number, e.g. a
            currency code.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    __get_pydantic_core_schema__ = _SchemaHook()  # type: ignore[assignment]  # pyright: ignore[reportAssignmentType]

    id: str
    style: Literal["percent", "multiple", "number", "integer", "compact"]
    suffix: str = ""
    prefix_field: str | None = None


FRACTION = Unit(id="fraction", style="percent")
FRACTION_PER_YEAR = Unit(id="fraction_per_year", style="percent", suffix="/yr")
MULTIPLE = Unit(id="multiple", style="multiple", suffix="×")
NUMBER = Unit(id="number", style="number")
COUNT = Unit(id="count", style="integer")
BARS = Unit(id="bars", style="integer", suffix=" bars")
DAYS = Unit(id="days", style="integer", suffix=" days")
YEARS = Unit(id="years", style="number", suffix=" years")

_COMPACT = ((1e12, "tn"), (1e9, "bn"), (1e6, "m"), (1e3, "k"))


def _sig(x: float, figures: int = 3) -> str:
    """`x` to `figures` significant figures: never scientific notation, never rounds a non-zero to 0.

    Integer digits are kept whole (1234 stays "1234"); trailing zeros after the point are dropped.
    """
    if x == 0:
        return "0"
    decimals = max(0, figures - 1 - math.floor(math.log10(abs(x))))
    text = f"{round(x, decimals):.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _body(value: float, unit: Unit) -> str:
    """The number part of a formatted value (sign included, prefix and suffix excluded)."""
    if unit.style == "percent":
        return _sig(value * 100) + "%"
    if unit.style == "integer":
        return str(round(value))
    if unit.style == "compact":
        for i, (scale, name) in enumerate(_COMPACT):
            if abs(value) >= scale:
                if abs(float(_sig(value / scale))) >= 1000 and i > 0:  # 999,999 -> 1m, not 1000k
                    scale, name = _COMPACT[i - 1]
                return _sig(value / scale) + name
        return _sig(value)
    return _sig(value)  # "number" and "multiple" (its "×" is the unit's suffix)


def format_value(
    value: float | int | None,  # noqa: PYI041  # spelled out to match the documented interface
    unit: Unit,
    row: Mapping[str, Any] | None = None,
    *,
    signed: bool = False,
) -> str | None:
    """Format `value` by `unit`, or None when `value` is None (rendered `null` in evidence).

    3 significant figures, no scientific notation, a non-zero value never prints as zero.
    `row` supplies the sibling value for `unit.prefix_field` (ignored when absent or null);
    `signed` adds "+" to positive values. The only formatter; see core.md, Units.
    """
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return str(number)
    text = _body(number, unit) + unit.suffix
    if signed and number > 0:
        text = "+" + text
    prefix = row.get(unit.prefix_field) if row is not None and unit.prefix_field else None
    return f"{prefix} {text}" if prefix is not None else text


def _units_in(metadata: typing.Iterable[Any]) -> Unit | None:
    return next((m for m in metadata if isinstance(m, Unit)), None)


def _frame_fields(model: type[pa.DataFrameModel]) -> dict[str, Any]:
    """Attribute name -> pandera `FieldInfo` for every declared column."""
    return {info.original_name: info for _, info in model.__fields__.values()}


def unit_of(model: type, field: str) -> Unit | None:
    """The unit declared on `field` of a pydantic model or pandera frame model, else None.

    Pydantic: a `Unit` in the field's `Annotated` metadata. Pandera: `Field(metadata={"unit": ...})`.
    Inherited fields count (the MRO is walked, as glossary claims are).
    """
    if issubclass(model, pa.DataFrameModel):
        info = _frame_fields(model).get(field)
        unit = (info.metadata or {}).get("unit") if info is not None else None
        return unit if isinstance(unit, Unit) else None
    for cls in model.__mro__:
        fields = getattr(cls, "model_fields", None)
        if fields and field in fields:
            return _units_in(fields[field].metadata)
    return None


def _is_numeric_annotation(annotation: Any) -> bool:
    """int or float (also inside Optional/Union/Annotated), not bool."""
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _is_numeric_annotation(typing.get_args(annotation)[0])
    if origin is typing.Union or origin is UnionType:
        return any(_is_numeric_annotation(a) for a in typing.get_args(annotation))
    return isinstance(annotation, type) and issubclass(annotation, int | float) and not issubclass(annotation, bool)


def is_numeric_field(model: type, field: str) -> bool:
    """Whether `field` of a pydantic or pandera model holds a number (int or float, not bool)."""
    if issubclass(model, pa.DataFrameModel):
        column = model.to_schema().columns.get(_frame_fields(model)[field].name)
        dtype = column.dtype.type if column is not None and column.dtype is not None else None
        return dtype is not None and pd.api.types.is_numeric_dtype(dtype) and not pd.api.types.is_bool_dtype(dtype)
    info = model.model_fields[field]  # type: ignore[attr-defined]
    return _is_numeric_annotation(info.annotation)
