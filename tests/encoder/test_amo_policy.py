import itertools

import pytest
from pysat.solvers import Solver

from hermax.encoder._packed import encode_amo


@pytest.mark.parametrize('equality', [False, True])
@pytest.mark.parametrize('count', [0, 1, 2, 5, 6, 7, 9, 16, 32, 1024])
def test_automatic_amo_size_and_reserved_ids(count, equality):
    cnf = encode_amo(list(range(1, count + 1)), top_id=2000, equality=equality)
    cutoff = 5 if equality else 6
    if count <= cutoff:
        assert cnf.nv == 2000
        assert len(cnf.clauses) == count * (count - 1) // 2 + equality
    else:
        assert cnf.nv == 2000 + count - 1
        assert len(cnf.clauses) == 3 * count - 3
    assert all(0 < abs(lit) <= count or 2000 < abs(lit) <= cnf.nv
               for clause in cnf.clauses for lit in clause)


@pytest.mark.parametrize('equality', [False, True])
@pytest.mark.parametrize('count', [2, 5, 6, 7, 8])
def test_automatic_amo_preserves_complete_input_propagation(count, equality):
    cnf = encode_amo(list(range(1, count + 1)), top_id=count, equality=equality)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product([-1, 0, 1], repeat=count):
            assumptions = [i * value for i, value in enumerate(values, 1) if value]
            selected, unknown = values.count(1), values.count(0)
            expected_ok = selected <= 1 and (not equality or selected + unknown >= 1)
            ok, propagated = solver.propagate(assumptions=assumptions)
            assert ok == expected_ok
            if ok:
                expected = set(assumptions)
                if selected == 1:
                    expected.update(-i for i, value in enumerate(values, 1) if value == 0)
                elif equality and unknown == 1:
                    expected.update(i for i, value in enumerate(values, 1) if value == 0)
                assert {lit for lit in propagated if abs(lit) <= count} == expected


@pytest.mark.parametrize('equality', [False, True])
@pytest.mark.parametrize('lits', [[1, -2, 3, -4, 5, -6, 7, -8],
                                 [1, 1, 2], [1, -1, 2],
                                 [1, -2, -2, 3, 4, 5, 6, 7]])
def test_automatic_amo_signed_and_repeated_literals(lits, equality):
    count = max(map(abs, lits))
    cnf = encode_amo(lits, top_id=count, equality=equality)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product([False, True], repeat=count):
            selected = sum(values[abs(lit) - 1] if lit > 0 else not values[-lit - 1]
                           for lit in lits)
            assumptions = [i if value else -i for i, value in enumerate(values, 1)]
            assert solver.solve(assumptions=assumptions) == (selected == 1 if equality else selected <= 1)


@pytest.mark.parametrize('equality', [False, True])
@pytest.mark.parametrize('selected', [None, 0, 3, 6])
def test_counter_helpers_have_a_unique_assignment(equality, selected):
    cnf = encode_amo(list(range(1, 8)), top_id=20, equality=equality)
    assumptions = [i + 1 if i == selected else -(i + 1) for i in range(7)]
    with Solver(bootstrap_with=cnf.clauses) as solver:
        if equality and selected is None:
            assert not solver.solve(assumptions=assumptions)
            return
        assert solver.solve(assumptions=assumptions)
        helpers = [lit for lit in solver.get_model() if abs(lit) > 20]
        assert len(helpers) == 6
        solver.add_clause([-lit for lit in helpers])
        assert not solver.solve(assumptions=assumptions)


@pytest.mark.parametrize('lits', [[0], [True], [1 << 40], [-(1 << 31)]])
def test_native_amo_rejects_invalid_literal_ids(lits):
    with pytest.raises((TypeError, ValueError, OverflowError)):
        encode_amo(lits, top_id=0)
