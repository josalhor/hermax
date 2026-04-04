import pytest
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

