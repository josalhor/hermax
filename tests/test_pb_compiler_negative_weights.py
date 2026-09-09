import pytest
from pysat.solvers import Solver

from hermax.encoder.pb import PBCompiler, PBItem
from hermax.encoder.pbamo import PBAMOEnc


def _compiled_clauses(item: PBItem):
    compiled = PBCompiler.compile_batch([item], [], [], top_id=2)
    return [clause for formula in compiled for clause in formula.clauses]


def _satisfies_compiled(item: PBItem, values: tuple[bool, ...]) -> bool:
    with Solver(bootstrap_with=_compiled_clauses(item)) as solver:
        assumptions = [index if value else -index for index, value in enumerate(values, start=1)]
        return solver.solve(assumptions=assumptions)


@pytest.mark.parametrize(
    ("weights", "bound", "cmp_op"),
    [([-3, 2], -1, "<="), ([-3, 2], -1, "=="), ([3, -2], 1, "==")],
)
def test_pbcompiler_normalizes_signed_weights_semantically(weights, bound, cmp_op):
    item = PBItem([1, 2], bound, weights, cmp_op)

    for x in (False, True):
        for y in (False, True):
            total = weights[0] * x + weights[1] * y
            expected = total <= bound if cmp_op == "<=" else total == bound
            assert _satisfies_compiled(item, (x, y)) is expected


def test_pbcompiler_normalization_does_not_mutate_the_input():
    item = PBItem([1, -1, 2], bound=4, weights=[2, -3, 0], cmp_op="<=")

    _compiled_clauses(item)

    assert (item.lits, item.weights, item.bound) == ([1, -1, 2], [2, -3, 0], 4)


def test_direct_pbamo_requires_canonical_non_negative_weights():
    with pytest.raises(ValueError, match="non-negative"):
        PBAMOEnc.auto_eq(lits=[1, 2], weights=[1, -2], bound=1, top_id=2)


def test_pbcompiler_rejects_unsupported_comparison_operator():
    with pytest.raises(ValueError, match="comparison|operator|cmp_op"):
        PBCompiler.compile_batch(
            [PBItem([1, 2], bound=1, weights=[1, 1], cmp_op=">=")],
            [],
            [],
            top_id=2,
        )


def test_pbcompiler_rejects_non_integer_weights_without_truncation():
    with pytest.raises(ValueError, match="integers"):
        _compiled_clauses(PBItem([1, 2], 1, [1.5, 0], "<="))


def test_pbcompiler_rejects_non_integer_bounds_without_truncation():
    with pytest.raises(ValueError, match="bound"):
        _compiled_clauses(PBItem([1, 2], -0.5, [1, 1], "<="))
