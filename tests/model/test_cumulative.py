import pytest
import random
from hermax.model import Model

def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r

@pytest.mark.parametrize("backend", ["auto", "time", "task"])
def test_cumulative_rejects_overload_and_allows_feasible_schedule(backend):
    m_unsat = Model()
    s1u = m_unsat.int("s1", 0, 5)
    s2u = m_unsat.int("s2", 0, 5)
    m_unsat &= (s1u == 0)
    m_unsat &= (s2u == 0)
    m_unsat.cumulative([s1u, s2u], [2, 2], [2, 2], 3, backend=backend)
    assert m_unsat.solve().status == "unsat"

    m_sat = Model()
    s1 = m_sat.int("s1", 0, 5)
    s2 = m_sat.int("s2", 0, 5)
    m_sat &= (s1 == 0)
    m_sat &= (s2 == 2)
    m_sat.cumulative([s1, s2], [2, 2], [2, 2], 3, backend=backend)
    r = _solve_ok(m_sat)
    assert r[s1] == 0
    assert r[s2] == 2


def test_cumulative_random_fixed_schedules_match_direct_capacity_check():
    rng = random.Random(3)

    for backend in ["auto", "time", "task"]:
        for case in range(18):
            starts = [rng.randint(0, 4) for _ in range(3)]
            durations = [rng.randint(1, 3) for _ in range(3)]
            demands = [rng.randint(1, 3) for _ in range(3)]
            capacity = rng.randint(1, 5)

            overload = False
            horizon = max(s + d for s, d in zip(starts, durations))
            for t in range(horizon):
                load = sum(
                    demand
                    for start, duration, demand in zip(starts, durations, demands)
                    if start <= t < start + duration
                )
                if load > capacity:
                    overload = True
                    break

            m = Model()
            vars_ = [m.int(f"s_{backend}_{case}_{i}", 0, 6) for i in range(3)]
            for v, start in zip(vars_, starts):
                m &= (v == start)
            m.cumulative(vars_, durations, demands, capacity, backend=backend)
            status = m.solve().status
            assert status == ("unsat" if overload else "sat")
