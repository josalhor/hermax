import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model.expressions import sum_expr


def test_sparse_weighted_output_does_not_create_predicates_for_gaps():
    m=Model();bits=list(m.bool_vector('b',12));total=m.int('total',0,1200)
    before=len(m.to_cnf().clauses)
    m &= total==sum_expr(100*b for b in bits)
    assert len(m.to_cnf().clauses)-before<500
    assert all(value%100==0 for value in total._eq_lits)


@pytest.mark.parametrize('weights',[(3,6,9,12),(7,11,13,17)])
@pytest.mark.parametrize('extra',[0,5])
@pytest.mark.parametrize('exactly_one',[False,True])
def test_compact_outputs_match_arithmetic(weights,extra,exactly_one):
    m=Model();bits=list(m.bool_vector('b',4));total=m.int('total',0,sum(weights)+extra)
    if exactly_one:m &= sum_expr(bits)==1
    m &= total==sum_expr(w*b for w,b in zip(weights,bits))
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for values,value in itertools.product(itertools.product((False,True),repeat=4),range(total.ub+1)):
            expected=value==sum(w*v for w,v in zip(weights,values)) and (not exactly_one or sum(values)==1)
            assumptions=[b.id if v else -b.id for b,v in zip(bits,values)]
            assumptions.extend(m._lit_to_dimacs(total>=k) if value>=k else -m._lit_to_dimacs(total>=k) for k in range(1,total.ub+1))
            assert solver.solve(assumptions=assumptions)==expected


def test_constant_exactly_one_cost_has_only_one_output_value():
    m=Model();bits=list(m.bool_vector('b',4));total=m.int('total',0,100)
    m &= sum_expr(bits)==1
    m &= total==sum_expr(25*b for b in bits)
    assert set(total._eq_lits)<= {25}
    result=m.solve()
    assert result[total]==25
