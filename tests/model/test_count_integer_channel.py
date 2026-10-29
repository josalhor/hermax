import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model.expressions import sum_expr


def test_narrow_total_uses_bounded_counter():
    m=Model();bits=m.bool_vector('b',256);total=m.int('total',0,3)
    m &= total==sum_expr(bits)
    assert len(m.to_cnf().clauses)<5000


def test_impossible_upper_region_needs_one_boundary_cut():
    counts=[]
    for upper in (100,1000):
        m=Model();bits=m.bool_vector('b',8);total=m.int('total',0,upper)
        before=len(m.to_cnf().clauses)
        m &= total==sum_expr(bits)
        counts.append(len(m.to_cnf().clauses)-before)
    assert counts[0]==counts[1]


@pytest.mark.parametrize('bounds',[(-5,-2),(-3,2),(0,2),(2,4),(0,9),(8,10)])
@pytest.mark.parametrize('op',['==','<=','>=','<','>'])
@pytest.mark.parametrize('shift',[-2,0,3])
def test_channel_matches_arithmetic(bounds,op,shift):
    m=Model();bits=list(m.bool_vector('b',3));total=m.int('total',*bounds)
    expr=sum_expr(bits)+shift
    m &= {'==':total.__eq__,'<=':total.__le__,'>=':total.__ge__,'<':total.__lt__,'>':total.__gt__}[op](expr)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        cuts=[m._lit_to_dimacs(total>=k) for k in range(total.lb+1,total.ub+1)]
        for values,value in itertools.product(itertools.product((False,True),repeat=3),range(total.lb,total.ub+1)):
            assumptions=[lit.id if v else -lit.id for lit,v in zip(bits,values)]
            assumptions.extend(lit if value>=k else -lit for k,lit in enumerate(cuts,total.lb+1))
            rhs=sum(values)+shift
            expected={'==':value==rhs,'<=':value<=rhs,'>=':value>=rhs,'<':value<rhs,'>':value>rhs}[op]
            assert solver.solve(assumptions=assumptions)==expected
