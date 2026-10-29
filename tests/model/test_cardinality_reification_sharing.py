import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model.expressions import sum_expr


@pytest.mark.parametrize('equality',[False,True])
def test_reified_one_count_shares_counter(equality):
    m=Model();bits=m.bool_vector('b',512);r=m.bool('r');expr=sum_expr(bits)
    m &= (expr==1).iff(r) if equality else (expr<=1).iff(r)
    c=m.to_cnf()
    assert len(c.clauses)<5000
    assert c.nv<2500


@pytest.mark.parametrize('n',range(6))
@pytest.mark.parametrize('equality',[False,True])
@pytest.mark.parametrize('signed',[False,True])
@pytest.mark.parametrize('gated',[False,True])
def test_reified_count_matches_arithmetic(n,equality,signed,gated):
    m=Model();bits=list(m.bool_vector('b',n));r=m.bool('r');gate=m.bool('gate')
    inputs=[~b if signed and i%2 else b for i,b in enumerate(bits)]
    expr=sum_expr(inputs,start=2)
    # Keep the empty case a PB descriptor too.
    if n==0:expr=sum_expr([0*r,2])
    condition=(expr==3) if equality else (expr<=3)
    if gated:condition=condition.only_if(gate)
    m &= condition.iff(~r)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for values,rv,gv in itertools.product(itertools.product((False,True),repeat=n),(False,True),(False,True)):
            count=sum(not v if signed and i%2 else v for i,v in enumerate(values))
            truth=count==1 if equality else count<=1
            if gated:truth=not gv or truth
            assumptions=[b.id if v else -b.id for b,v in zip(bits,values)]
            assumptions += [r.id if rv else -r.id,gate.id if gv else -gate.id]
            assert solver.solve(assumptions=assumptions)==((not rv)==truth)


@pytest.mark.parametrize('op',['!=','<','>','>=','=='])
def test_other_comparisons_and_reversed_counts_remain_sound(op):
    m=Model();bits=list(m.bool_vector('b',4));r=m.bool('r');expr=sum_expr(bits)
    condition={'!=':expr.__ne__,'<':expr.__lt__,'>':expr.__gt__,'>=':expr.__ge__,'==':expr.__eq__}[op](3)
    m &= condition.iff(r)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for values,rv in itertools.product(itertools.product((False,True),repeat=4),(False,True)):
            count=sum(values)
            truth={'!=':count!=3,'<':count<3,'>':count>3,'>=':count>=3,'==':count==3}[op]
            assumptions=[b.id if v else -b.id for b,v in zip(bits,values)]+[r.id if rv else -r.id]
            assert solver.solve(assumptions=assumptions)==(rv==truth)
