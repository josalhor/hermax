import itertools
import pytest
from hermax.model import Model
from hermax.model.expressions import sum_expr


def test_redundant_bigm_branch_matches_guarded_encoding_size():
    counts = []
    for bigm in (False, True):
        m = Model()
        bits = m.bool_vector('b', 256)
        gate = m.bool('gate')
        x = m.int('x', 0, 10)
        expr = x + sum_expr(bits)
        m &= (expr <= 3 + 266 * gate) if bigm else (expr <= 3).only_if(~gate)
        cnf = m.to_cnf()
        counts.append((len(cnf.clauses), cnf.nv))
    assert counts[0] == counts[1]


@pytest.mark.parametrize('op', ['<=', '<', '>=', '>'])
@pytest.mark.parametrize('coefficient', [-2, 1])
@pytest.mark.parametrize('negated', [False, True])
@pytest.mark.parametrize('reverse', [False, True])
def test_bigm_reduction_matches_arithmetic(op, coefficient, negated, reverse):
    m = Model()
    x = m.int('x', -1, 2)
    a, b, gate = m.bool('a'), m.bool('b'), m.bool('gate')
    indicator = ~gate if negated else gate
    expr = coefficient * x + a + b + 3
    scale = 20 if op in ('<=', '<') else -20
    base = 4 + scale if reverse else 4
    scale = -scale if reverse else scale
    rhs = base + scale * indicator
    m &= {'<=': expr.__le__, '<': expr.__lt__, '>=': expr.__ge__, '>': expr.__gt__}[op](rhs)
    for xv, av, bv, gv in itertools.product(range(-1, 3), (False, True), (False, True), (False, True)):
        lhs = coefficient * xv + av + bv + 3
        bound = base + scale * (not gv if negated else gv)
        expected = {'<=': lhs <= bound, '<': lhs < bound, '>=': lhs >= bound, '>': lhs > bound}[op]
        assumptions = [x == xv, a if av else ~a, b if bv else ~b, gate if gv else ~gate]
        assert (m.solve(assumptions=assumptions).status != 'unsat') == expected
