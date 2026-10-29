import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


def _feasible(starts, durations, demands, capacity):
    times = {t for s, d in zip(starts, durations) for t in range(s, s + d)}
    return all(
        sum(r for s, d, r in zip(starts, durations, demands) if s <= t < s + d)
        <= capacity
        for t in times
    )


@pytest.mark.parametrize("backend", ["auto", "time", "task"])
@pytest.mark.parametrize("mode", ["post", "only_if", "implies", "iff", "gated_iff"])
@pytest.mark.parametrize(
    "durations,demands,capacity",
    [([2, 2], [2, 2], 3), ([0, 2], [9, 1], 0), ([1, 2], [0, 1], 1)],
)
def test_cumulative_composition_truth_table(
    backend, mode, durations, demands, capacity
):
    m = Model()
    starts = m.int_vector("s", 2, -1, 1)
    flag = m.bool("flag")
    gate = m.bool("gate")
    before = m._next_id, len(m._hard)
    condition = m.cumulative(starts, durations, demands, capacity, backend=backend)
    assert (m._next_id, len(m._hard)) == before
    if mode == "only_if":
        condition = condition.only_if(flag)
    elif mode == "implies":
        condition = condition.implies(flag)
    elif mode == "iff":
        condition = condition.iff(flag)
    elif mode == "gated_iff":
        condition = condition.only_if(gate).iff(flag)
    m &= condition
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, f, g in itertools.product(
            range(-1, 2), range(-1, 2), (False, True), (False, True)
        ):
            expected = _feasible([a, b], durations, demands, capacity)
            if mode == "only_if":
                expected = not f or expected
            elif mode == "implies":
                expected = not expected or f
            elif mode == "iff":
                expected = f == expected
            elif mode == "gated_iff":
                expected = f == (not g or expected)
            fixed = [
                m._lit_to_dimacs(lit)
                for var, val in zip(starts, [a, b])
                for lit in var._exact_value_atoms(val)
            ]
            fixed += [
                m._lit_to_dimacs(flag if f else ~flag),
                m._lit_to_dimacs(gate if g else ~gate),
            ]
            assert solver.solve(assumptions=fixed) is expected, (a, b, f, g)


def test_unposted_cumulative_does_not_constrain_the_model():
    m = Model()
    s = m.int_vector("s", 2, 0, 2)
    m &= s[0] == 0
    m &= s[1] == 0
    condition = m.cumulative(s, [2, 2], [1, 1], 1)
    assert m.solve().ok
    m &= condition
    assert not m.solve().ok


@pytest.mark.parametrize("mode", ["post", "iff"])
def test_empty_cumulative_is_true(mode):
    m = Model()
    flag = m.bool()
    condition = m.cumulative([], [], [], 0)
    m &= condition.iff(flag) if mode == "iff" else condition
    m &= ~flag
    assert m.solve().ok is (mode == "post")


def test_reified_cumulative_does_not_expand_large_gaps_between_domains():
    m = Model()
    a = m.int("a", 0, 2)
    b = m.int("b", 10**9, 10**9 + 2)
    flag = m.bool()
    m &= m.cumulative([a, b], [2, 2], [1, 1], 1).iff(flag)
    cnf = m.to_cnf()
    assert cnf.nv < 100 and len(cnf.clauses) < 100
    m &= ~flag
    assert not m.solve().ok


def test_cumulative_captures_input_sequences_without_posting():
    m = Model()
    s = m.int_vector("s", 2, 0, 1)
    durations = [2, 2]
    condition = m.cumulative(s, durations, [1, 1], 1)
    durations[1] = 0
    m &= s[0] == 0
    m &= s[1] == 0
    m &= condition
    assert not m.solve().ok


@pytest.mark.parametrize("backend", ["time", "task"])
def test_cumulative_indicator_can_be_a_start_threshold(backend):
    m = Model()
    s = m.int_vector("s", 2, 0, 2)
    flag = s[0] >= 1
    m &= m.cumulative(s, [2, 2], [1, 1], 1, backend=backend).iff(flag)
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b in itertools.product(range(3), repeat=2):
            fixed = [
                m._lit_to_dimacs(lit)
                for v, value in zip(s, [a, b])
                for lit in v._exact_value_atoms(value)
            ]
            assert solver.solve(assumptions=fixed) is (
                (a >= 1) == _feasible([a, b], [2, 2], [1, 1], 1)
            )


def test_cumulative_or_literal_requires_explicit_gating():
    m = Model()
    starts = m.int_vector("s", 3, 0, 3)
    flag = m.bool()
    condition = m.cumulative(starts, [2, 2, 2], [1, 1, 1], 2)
    before = m._next_id, len(m._hard)
    with pytest.raises(TypeError):
        _ = condition | flag
    with pytest.raises(TypeError):
        _ = flag | condition
    assert (m._next_id, len(m._hard)) == before
    m &= condition.only_if(~flag)
