import inspect
from typing import ClassVar

import pytest
from lensgraph.node import FetchNode, GlobalFailure, Node, NodeContext
from lensgraph.types import ContractViolation, Failed, UpstreamFailed
from pydantic import ValidationError
from toy.nodes import AssayClean, GrowthRate


@pytest.fixture
def s3_frame(toy_source):
    return toy_source.assays("S3")


def test_output_contract_pandera_rejects_missing_column(s3_frame):
    with pytest.raises(ContractViolation, match="assay_clean"):
        AssayClean().validate_output(s3_frame)


def test_output_contract_accepts_valid_frame(toy_source):
    frame = toy_source.assays("S1")
    assert AssayClean().validate_output(frame) is not None


def test_output_contract_type_mismatch():
    with pytest.raises(ContractViolation, match="growth_rate"):
        GrowthRate().validate_output("x")


def test_params_are_fields_and_unknown_rejected():
    assert GrowthRate.model_validate({"window": 7}).window == 7
    with pytest.raises(ValidationError):
        GrowthRate.model_validate({"windw": 7})


def test_code_version_changes_with_version_classvar():
    class A(GrowthRate):
        version: ClassVar[str] = "1"

    class B(GrowthRate):
        version: ClassVar[str] = "2"

    assert A.code_version() != B.code_version()


def test_fetch_code_version_ignores_source():
    class F1(FetchNode):
        name: ClassVar[str] = "f"

        def run(self, ctx):
            return 1

    class F2(FetchNode):
        name: ClassVar[str] = "f"

        def run(self, ctx):
            return 2

    assert F1.code_version() == F2.code_version()


def test_default_on_upstream_failure_raises():
    failure = Failed(origin="x", candidate="S1", error="e")
    ctx = NodeContext(run_id="r", candidate=None)
    with pytest.raises(UpstreamFailed) as exc:
        GrowthRate().on_upstream_failure(ctx, failure)
    assert exc.value.failure == failure


def test_check_inputs_required_columns_param(s3_frame):
    with pytest.raises(ContractViolation, match="od600"):
        AssayClean().check_inputs(raw=s3_frame)
    AssayClean(required_columns=["time_h"]).check_inputs(raw=s3_frame)


def test_global_failure_reexported():
    assert issubclass(GlobalFailure, Exception)


def test_non_plain_type_output_raises_contract_violation():
    class UnionOut(GrowthRate):
        name: ClassVar[str] = "union_out"
        output: ClassVar = int | str  # no __name__

    with pytest.raises(ContractViolation, match="union_out"):
        UnionOut().validate_output(1.5)


def _make_a():
    class Base(Node):
        name: ClassVar[str] = "n"

        def run(self, ctx):
            return 1

    class Sub(Base):
        pass

    return Sub


def _make_b():
    class Base(Node):
        name: ClassVar[str] = "n"

        def run(self, ctx):
            return 2

    class Sub(Base):
        pass

    return Sub


def test_code_version_covers_node_base_class_source():
    """Editing a base's logic must invalidate subclasses' memoized outputs."""
    a, b = _make_a(), _make_b()
    assert inspect.getsource(a) == inspect.getsource(b)
    assert a.code_version() != b.code_version()


def _helper(x):
    return x + 1


def test_code_deps_change_code_version():
    import types

    class Plain(GrowthRate):
        pass

    class WithFn(GrowthRate):
        code_deps: ClassVar[tuple] = (_helper,)

    class WithModule(GrowthRate):
        code_deps: ClassVar[tuple] = (types,)

    assert WithFn.code_version() != Plain.code_version()
    assert WithModule.code_version() not in {Plain.code_version(), WithFn.code_version()}


def test_code_version_unchanged_without_code_deps():
    import hashlib

    class Plain(GrowthRate):
        pass

    material = Plain.version + "".join(
        inspect.getsource(c) for c in Plain.__mro__ if issubclass(c, Node)
    )
    assert Plain.code_version() == hashlib.sha256(material.encode()).hexdigest()[:16]
