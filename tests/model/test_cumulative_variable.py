"""Variable cumulative semantics, checked against direct integer evaluation."""
import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


def feasible(starts, durations, demands, capacity):
    if min([capacity, *durations, *demands]) < 0:
        return False
    return all(sum(r for s, d, r in zip(starts, durations, demands)
                   if s <= t < s + d) <= capacity
               for t in starts)


@pytest.mark.parametrize('backend', ['auto', 'time', 'task'])
@pytest.mark.parametrize('mode', ['post', 'only_if', 'iff', 'implies'])
def test_variable_cumulative_truth_table(backend, mode):
    m = Model()
    starts = [m.int('s0', -1, 0), m.int('s1', 0, 1)]
    durations = [m.int('d', -1, 2), 1]
    demands = [m.int('r', -1, 2), 1]
    capacity = m.int('c', -1, 2)
    flag = m.bool('flag')
    before = m._next_id, len(m._hard)
    constraint = m.cumulative(starts, durations, demands, capacity, backend=backend)
    assert (m._next_id, len(m._hard)) == before
    m &= constraint if mode == 'post' else getattr(constraint, mode)(flag)
    variables = [*starts, durations[0], demands[0], capacity]
    # Materialize assumption atoms before exporting, including binary domains.
    domains = [range(v.lb, v.ub + 1) for v in variables]
    atoms = [{x: [m._lit_to_dimacs(a) for a in v._exact_value_atoms(x)]
              for x in domain} for v, domain in zip(variables, domains)]
    with Solver(name='g4', bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(*domains):
            valid = feasible(values[:2], [values[2], 1], [values[3], 1], values[4])
            for flag_value in (False, True):
                expected = {'post': valid, 'only_if': not flag_value or valid,
                            'iff': flag_value == valid, 'implies': not valid or flag_value}[mode]
                assumptions = [a for lookup, x in zip(atoms, values) for a in lookup[x]]
                assumptions.append(flag.id if flag_value else -flag.id)
                assert solver.solve(assumptions=assumptions) == expected, (values, flag_value)


@pytest.mark.parametrize('position', ['duration', 'demand', 'capacity'])
def test_variable_cumulative_rejects_foreign_model(position):
    m, other = Model(), Model()
    s = m.int('s', 0, 1)
    foreign = other.int('foreign', 0, 2)
    with pytest.raises(ValueError, match='different models'):
        m.cumulative([s], [foreign if position == 'duration' else 1],
                     [foreign if position == 'demand' else 1],
                     foreign if position == 'capacity' else 1)


def test_empty_variable_capacity_and_unposted_constraint():
    m = Model()
    cap = m.int('cap', -1, 1)
    constraint = m.cumulative([], [], [], cap)
    m &= cap == -1
    assert m.solve().ok
    m &= constraint
    assert m.solve().status == 'unsat'


@pytest.mark.parametrize('binary', [False, True])
@pytest.mark.parametrize('backend', ['auto', 'time', 'task'])
def test_three_variable_jobs_match_direct_loads(binary, backend):
    import random
    m = Model()
    m.set_integer_binary_threshold(2 if binary else None)
    starts = [m.int(f's{i}', -1, 2) for i in range(3)]
    durations = [m.int(f'd{i}', 0, 2) for i in range(3)]
    demands = [m.int(f'r{i}', 0, 2) for i in range(3)]
    capacity = m.int('cap', 0, 3)
    flag = m.bool()
    condition = m.cumulative(starts, durations, demands, capacity, backend=backend)
    m &= condition.iff(flag)
    variables = [*starts, *durations, *demands, capacity]
    atoms = [{x: [m._lit_to_dimacs(a) for a in v._exact_value_atoms(x)]
              for x in range(v.lb, v.ub + 1)} for v in variables]
    rng = random.Random(71)
    with Solver(name='g4', bootstrap_with=m.to_cnf().clauses) as solver:
        for _ in range(300):
            values = [rng.randint(v.lb, v.ub) for v in variables]
            expected = feasible(values[:3], values[3:6], values[6:9], values[9])
            assumptions = [a for lookup, x in zip(atoms, values) for a in lookup[x]]
            assert solver.solve(assumptions=assumptions + [flag.id if expected else -flag.id])
            assert not solver.solve(assumptions=assumptions + [-flag.id if expected else flag.id])


@pytest.mark.parametrize('backend', ['auto', 'time', 'task'])
def test_zero_fixed_duration_does_not_consume_variable_capacity(backend):
    m = Model()
    starts = [m.int('s0', 0, 1), m.int('s1', 0, 1)]
    cap = m.int('cap', 0, 2)
    m &= m.cumulative(starts, [0, 1], [100, 1], cap, backend=backend)
    m &= cap == 1
    assert m.solve().ok


def test_wide_binary_start_domains_use_actual_events():
    m = Model()
    starts = [m.int(f's{i}', 0, 10**6) for i in range(2)]
    durations = [m.int(f'd{i}', 0, 2) for i in range(2)]
    m &= m.cumulative(starts, durations, [1, 1], 1)
    cnf = m.to_cnf()
    assert cnf.nv < 10000
    assert len(cnf.clauses) < 30000
    m &= starts[0] == 500000
    m &= starts[1] == 500000
    m &= durations[0] == 1
    m &= durations[1] == 1
    assert m.solve().status == 'unsat'


def test_capacity_lower_bound_propagates_from_fixed_overlap():
    m = Model()
    s = [m.int(f's{i}', 0, 0) for i in range(2)]
    cap = m.int('cap', 0, 4)
    m &= m.cumulative(s, [2, 2], [1, 2], cap)
    threshold = m._lit_to_dimacs(cap >= 3)
    cnf = m.to_cnf()
    with Solver(name='g4', bootstrap_with=cnf.clauses) as solver:
        # Unit consequences may already have been consumed during bootstrap.
        ok, _ = solver.propagate(assumptions=[-threshold])
        assert not ok


@pytest.mark.parametrize('backend', ['auto', 'time', 'task'])
def test_post_variable_cumulative_after_live_sat_binding(backend):
    m = Model()
    starts = [m.int(f's{i}', 0, 2) for i in range(2)]
    duration = m.int('duration', 0, 2)
    demand = m.int('demand', 0, 2)
    cap = m.int('cap', 0, 3)
    assert m.solve(incremental=True, backend='sat').ok
    try:
        m &= m.cumulative(starts, [duration, 1], [demand, 1], cap, backend=backend)
        fixed = [starts[0] == 0, starts[1] == 0, duration == 1, demand == 2]
        assert m.solve(assumptions=[*fixed, cap == 3], backend='sat').ok
        assert m.solve(assumptions=[*fixed, cap == 2], backend='sat').status == 'unsat'
        assert m.solve(assumptions=[*fixed, cap == 3], backend='sat').ok
    finally:
        m.close_incremental()


@pytest.mark.parametrize('backend', ['auto', 'time', 'task'])
def test_no_overlap_accepts_variable_zero_duration(backend):
    m = Model()
    starts = [m.int('a', 0, 0), m.int('b', 0, 0)]
    duration = m.int('duration', 0, 1)
    m &= m.no_overlap(starts, [duration, 1], backend=backend)
    result = m.solve()
    assert result.ok and result[duration] == 0


def test_auto_retains_time_propagation_on_moderate_fixed_demand_horizons():
    m = Model()
    starts = m.int_vector('s', 4, 0, 8)
    duration = m.int('duration', 1, 3)
    fixed_demand = m.cumulative(starts, [duration] * 4, [1] * 4, 2)
    assert fixed_demand._encoding.backend == 'time'
    demand = m.int('demand', 0, 2)
    variable_demand = m.cumulative(starts, [duration] * 4, [demand] * 4, 2)
    assert variable_demand._encoding.backend == 'task'
