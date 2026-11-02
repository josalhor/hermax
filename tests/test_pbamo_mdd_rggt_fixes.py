"""Boundary, preprocessing and memory-path regressions for MDD/RGGT."""
import itertools
import subprocess
import sys

import pytest
from pysat.solvers import Solver

from tests.test_structuredpb_glpw import _unit_propagate


@pytest.mark.parametrize('encoder', ['mdd', 'rggt'])
@pytest.mark.parametrize('emit_amo', [False, True])
def test_overweight_terms_emit_units_and_preserve_original_amo(pbamo_module, encoder, emit_amo):
    from hermax.internal import _pbamo
    lits = [1, -2, 3, 4]
    groups = [[1, -2], [3, 4]]
    terms = list(zip(lits, [9, 2, 4, 6]))
    clauses, top = _pbamo.encode_leq(terms, groups, 5, 10, encoder, emit_amo)
    if not emit_amo:
        clauses += [[-a, -b] for group in groups for a, b in itertools.combinations(group, 2)]
    with Solver(bootstrap_with=clauses) as solver:
        for values in itertools.product([False, True], repeat=4):
            active = {lit: values[abs(lit)-1] == (lit > 0) for lit in lits}
            expected = sum(weight for lit, weight in terms if active[lit]) <= 5
            expected &= all(sum(active[lit] for lit in group) <= 1 for group in groups)
            assert solver.solve(assumptions=[i if v else -i for i, v in enumerate(values, 1)]) == expected
    assert top >= 10


@pytest.mark.parametrize('encoder', ['mdd', 'rggt'])
def test_zero_bound_has_only_units(pbamo_module, encoder):
    from hermax.internal import _pbamo
    n = 1024
    clauses, top = _pbamo.encode_leq([(i, i + 1) for i in range(1, n + 1)],
                                      [[i] for i in range(1, n + 1)], 0, n, encoder, False)
    assert top == n
    assert set(map(tuple, clauses)) == {(-i,) for i in range(1, n + 1)}


@pytest.mark.parametrize('encoder', ['mdd', 'rggt'])
def test_redundant_capacity_and_unsigned_overflow(pbamo_module, encoder):
    from hermax.internal import _pbamo
    n = 1024
    clauses, top = _pbamo.encode_leq([(i, 1) for i in range(1, n + 1)],
                                      [[i] for i in range(1, n + 1)], n, n, encoder, False)
    assert clauses == [] and top == n
    maximum = (1 << 64) - 1
    clauses, _ = _pbamo.encode_leq([(1, maximum), (2, 1)], [[1], [2]], maximum, 2, encoder, False)
    with Solver(bootstrap_with=clauses) as solver:
        assert not solver.solve(assumptions=[1, 2])
        assert solver.solve(assumptions=[1, -2])


@pytest.mark.parametrize('encoder', ['mdd', 'rggt'])
def test_complementary_weights_normalize_without_losing_amo_facts(pbamo_module, encoder):
    from hermax.internal import _pbamo
    lits = [-2, -1, 3, 2, 1]
    weights = [9, 7, 7, 3, 7]
    groups = [[-2, -1], [3, 2], [1]]
    clauses, _ = _pbamo.encode_leq(list(zip(lits, weights)), groups, 9, 3, encoder, True)
    # After cancellation, UP can establish this conflict. The old encoding
    # did not detect it without search.
    assert not _unit_propagate(clauses, [-3])[0]
    with Solver(bootstrap_with=clauses) as solver:
        for values in itertools.product([False, True], repeat=3):
            def value(lit): return values[abs(lit)-1] == (lit > 0)
            expected = sum(weight for lit, weight in zip(lits, weights) if value(lit)) <= 9
            expected &= all(sum(value(lit) for lit in group) <= 1 for group in groups)
            assert solver.solve(assumptions=[i if v else -i for i, v in enumerate(values, 1)]) == expected


@pytest.mark.parametrize('encoder', ['mdd', 'rggt'])
def test_cancelling_complements_can_make_constraint_unsatisfiable(pbamo_module, encoder):
    from hermax.internal import _pbamo
    clauses, _ = _pbamo.encode_leq([(1, 10), (-1, 9)], [[1], [-1]], 8, 1, encoder, False)
    assert [] in clauses


def test_mdd_deep_diagram_does_not_overflow_native_stack(pbamo_module):
    # Isolate the regression so an accidental native-stack overflow cannot
    # bring down the pytest process.
    code = '''
from hermax.internal import _pbamo
n = 40000
clauses, top = _pbamo.encode_leq([(i, 1) for i in range(1, n+1)],
                                  [[i] for i in range(1, n+1)], n-1, n, "mdd", False)
assert len(clauses) == n and top == 2*n-1
'''
    completed = subprocess.run([sys.executable, '-c', code], text=True, capture_output=True, timeout=20)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize('base,step,offset,bound', [(0, 1, 0, 900), (1_000_000, 1, 0, 2_000_900), (0, 10_000, 1, 9_000_000)])
def test_rggt_large_sum_domains_match_arithmetic(pbamo_module, base, step, offset, bound):
    from hermax.internal import _pbamo
    # A 514 x 514 product exercises the direct bitmap, offset bitmap and
    # sorted-row merge paths.
    n = 513
    terms = [(i, base + step * ((i - 1) % n + 1) + offset) for i in range(1, 2*n + 1)]
    groups = [list(range(1, n+1)), list(range(n+1, 2*n+1))]
    clauses, _ = _pbamo.encode_leq(terms, groups, bound, 2*n, 'rggt', False)
    with Solver(bootstrap_with=clauses) as solver:
        for a, b in [(1, 1), (1, 513), (200, 400), (450, 451), (513, 513)]:
            selected = {a, n+b}
            assumptions = [i if i in selected else -i for i in range(1, 2*n+1)]
            assert solver.solve(assumptions=assumptions) == (2*base + step*(a+b) + 2*offset <= bound)


@pytest.mark.parametrize('method', ['encode_leq', 'encode_eq'])
def test_rggt_balanced_fallback_for_many_distinct_domains(pbamo_module, method):
    from hermax.internal import _pbamo
    # More than 512 distinct leaf domains activates the bounded-memory tree.
    # Every two true inputs exceed the bound, while only the last weight
    # equals it. This exercises both upper-bound and equality trees.
    n = 513
    terms = [(i, 1_000_000 + i) for i in range(1, n + 1)]
    clauses, _ = getattr(_pbamo, method)(terms, [[i] for i in range(1, n + 1)],
                                         1_000_000 + n, n, 'rggt', False)
    with Solver(bootstrap_with=clauses) as solver:
        assert solver.solve(assumptions=[n])
        assert not solver.solve(assumptions=[1, n])
        assert solver.solve(assumptions=[1]) == (method == 'encode_leq')
        assert solver.solve(assumptions=[-i for i in range(1, n + 1)]) == (method == 'encode_leq')
