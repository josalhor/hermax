import builtins
import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.model import variables


@pytest.mark.parametrize("op", ["<=", "<", ">=", ">", "==", "distance"])
def test_narrow_domains_do_not_scan_numeric_gap(monkeypatch, op):
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 10**9, 10**9 + 10)

    def bounded_range(*args):
        result = builtins.range(*args)
        assert len(result) <= 100, "comparison scans numeric gap"
        return result

    monkeypatch.setattr(variables, "range", bounded_range, raising=False)
    relation = (
        x.distance_at_most(y, 20)
        if op == "distance"
        else x._relop_intvar(y, op)
        if op != "=="
        else x == y
    )
    assert len(relation) <= 1


@pytest.mark.parametrize("op", ["<=", "<", ">=", ">", "==", "distance"])
def test_comparisons_exact_for_all_values_and_reification(op):
    for lb1, lb2, width1, width2 in itertools.product(
        [-4, 0, 4], [-4, 0, 4], [0, 2], [0, 2]
    ):
        m = Model()
        x = m.int("x", lb1, lb1 + width1)
        y = m.int("y", lb2, lb2 + width2)
        b = m.bool("b")
        relation = (
            x.distance_at_most(y, 2)
            if op == "distance"
            else x == y
            if op == "=="
            else x._relop_intvar(y, op, 2)
        )
        m &= relation.iff(b)
        with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
            for a in range(x.lb, x.ub + 1):
                for c in range(y.lb, y.ub + 1):
                    expected = (
                        abs(a - c) <= 2
                        if op == "distance"
                        else a == c
                        if op == "=="
                        else {
                            "<=": a + 2 <= c,
                            "<": a + 2 < c,
                            ">=": a + 2 >= c,
                            ">": a + 2 > c,
                        }[op]
                    )
                    fixed = [
                        lit.id if i < value - owner.lb else -lit.id
                        for owner, value in [(x, a), (y, c)]
                        for i, lit in enumerate(owner._threshold_lits)
                    ]
                    for truth in (False, True):
                        assert solver.solve(
                            assumptions=fixed + [b.id if truth else -b.id]
                        ) == (truth == expected)


def test_large_shift_with_overlapping_effective_domains(monkeypatch):
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 10**9, 10**9 + 10)
    visited = 0

    def bounded_range(*args):
        nonlocal visited
        result = builtins.range(*args)
        assert len(result) <= 20
        visited += len(result)
        return result

    monkeypatch.setattr(variables, "range", bounded_range, raising=False)
    relation = x._relop_intvar(y, "<=", 10**9)
    assert len(relation) == 10
    assert visited == 10
    m &= relation
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, c in itertools.product(range(11), repeat=2):
            fixed = [
                lit.id if i < value else -lit.id
                for owner, value in [(x, a), (y, c)]
                for i, lit in enumerate(owner._threshold_lits)
            ]
            assert solver.solve(assumptions=fixed) == (a <= c)
