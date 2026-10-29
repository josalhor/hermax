import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model


def test_common_branch_bound_propagates_without_assigning_flag():
    m=Model();x=m.int('x',0,10);y=m.int('y',0,10);flag=m.bool('flag')
    m &= 3*x+7*y+flag<=50
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        ok,forced=solver.propagate(assumptions=[m._lit_to_dimacs(x>=1)])
        assert ok
        assert m._lit_to_dimacs(y<=6) in forced


def test_common_branch_clauses_reduce_encoding_size():
    m=Model();x=m.int('x',0,1000);y=m.int('y',0,1000);flag=m.bool('flag')
    before=len(m.to_cnf().clauses)
    m &= 10*x+11*y+flag<=10500
    assert len(m.to_cnf().clauses)-before==1001


@pytest.mark.parametrize('coefficients',[(3,7),(-3,7),(3,-7)])
@pytest.mark.parametrize('weight',[-2,1])
@pytest.mark.parametrize('op',['<=','<','>=','>','=='])
@pytest.mark.parametrize('reified',[False,True])
def test_factored_branches_match_arithmetic(coefficients,weight,op,reified):
    m=Model();x=m.int('x',-2,2);y=m.int('y',-1,3)
    flag,result=m.bool('flag'),m.bool('result')
    a,b=coefficients;expr=a*x+b*y+weight*~flag+2
    condition={'<=':expr.__le__,'<':expr.__lt__,'>=':expr.__ge__,'>':expr.__gt__,'==':expr.__eq__}[op](5)
    m &= condition.iff(result) if reified else condition
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for xv,yv,fv,rv in itertools.product(range(-2,3),range(-1,4),(False,True),(False,True)):
            value=a*xv+b*yv+weight*(not fv)+2
            truth={'<=':value<=5,'<':value<5,'>=':value>=5,'>':value>5,'==':value==5}[op]
            assumptions=[]
            for var,v in ((x,xv),(y,yv)):
                assumptions.extend(m._lit_to_dimacs(var>=k) if v>=k else -m._lit_to_dimacs(var>=k) for k in range(var.lb+1,var.ub+1))
            assumptions.extend([flag.id if fv else -flag.id,result.id if rv else -result.id])
            assert solver.solve(assumptions=assumptions)==((rv==truth) if reified else truth)
