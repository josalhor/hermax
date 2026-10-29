import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model


@pytest.mark.parametrize('coefficients',[(-7,-3),(-7,3),(2,-5),(1,10),(7,3)])
@pytest.mark.parametrize('target',[-20,-1,0,5,20])
@pytest.mark.parametrize('op',['<=','<','>=','>','=='])
@pytest.mark.parametrize('reified',[False,True])
def test_direct_boundary_emission_matches_arithmetic(coefficients,target,op,reified):
    m=Model();x=m.int('x',-3,2);y=m.int('y',1,4);indicator=m.bool('r')
    a,b=coefficients;expr=a*x+b*y+2
    condition={'<=':expr.__le__,'<':expr.__lt__,'>=':expr.__ge__,'>':expr.__gt__,'==':expr.__eq__}[op](target)
    m &= condition.iff(indicator) if reified else condition
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for xv,yv,flag in itertools.product(range(-3,3),range(1,5),(False,True)):
            actual=a*xv+b*yv+2
            truth={'<=':actual<=target,'<':actual<target,'>=':actual>=target,'>':actual>target,'==':actual==target}[op]
            assumptions=[]
            for var,value in ((x,xv),(y,yv)):
                assumptions.extend(m._lit_to_dimacs(var>=k) if value>=k else -m._lit_to_dimacs(var>=k) for k in range(var.lb+1,var.ub+1))
            assumptions.append(indicator.id if flag else -indicator.id)
            assert solver.solve(assumptions=assumptions)==((flag==truth) if reified else truth)


def test_repeated_rounded_bounds_need_only_the_weakest_implications():
    m=Model();x=m.int('x',0,10000);y=m.int('y',0,10000)
    before=len(m.to_cnf().clauses);top=m._top_id()
    m &= x+1000*y<=5000000
    cnf=m.to_cnf()
    assert len(cnf.clauses)-before==11
    assert cnf.nv==top
