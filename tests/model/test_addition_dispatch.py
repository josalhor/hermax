import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model


@pytest.mark.parametrize('op',['==','<=','<'])
def test_equivalent_addition_orientations_have_identical_encoding(op):
    outputs=[]
    for reverse in (False,True):
        m=Model();x=m.int('x',0,30);y=m.int('y',0,30);z=m.int('z',0,60)
        lhs,rhs=(z,x+y) if reverse else (x+y,z)
        cmp={'==':'==','<=':'>=','<':'>'}[op] if reverse else op
        m &= {'==':lhs.__eq__,'<=':lhs.__le__,'<':lhs.__lt__,'>=':lhs.__ge__,'>':lhs.__gt__}[cmp](rhs)
        c=m.to_cnf();outputs.append((c.clauses,c.nv))
    assert outputs[0]==outputs[1]


def test_narrow_sum_output_does_not_build_full_merge():
    m=Model();x=m.int('x',0,100);y=m.int('y',0,100);z=m.int('z',0,3)
    before=len(m.to_cnf().clauses);m &= x+y==z
    assert len(m.to_cnf().clauses)-before<1000


@pytest.mark.parametrize('op',['==','<=','<','>=','>'])
@pytest.mark.parametrize('offset',[-8,-2,0,3,10])
@pytest.mark.parametrize('general',[False,True])
def test_addition_channel_matches_arithmetic(op,offset,general,monkeypatch):
    if general:
        monkeypatch.setattr("hermax.model.encoders.addition_encoding",lambda *a,**kw:"general")
    m=Model();x=m.int('x',-2,2);y=m.int('y',1,4);z=m.int('z',-1,3)
    expr=x+y+offset
    m &= {'==':expr.__eq__,'<=':expr.__le__,'<':expr.__lt__,'>=':expr.__ge__,'>':expr.__gt__}[op](z)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(range(-2,3),range(1,5),range(-1,4)):
            assumptions=[]
            for v,value in zip((x,y,z),values):
                assumptions.extend(m._lit_to_dimacs(v>=k) if value>=k else -m._lit_to_dimacs(v>=k) for k in range(v.lb+1,v.ub+1))
            a=values[0]+values[1]+offset;b=values[2]
            expected={'==':a==b,'<=':a<=b,'<':a<b,'>=':a>=b,'>':a>b}[op]
            assert solver.solve(assumptions=assumptions)==expected


@pytest.mark.parametrize('op',['==','<='])
def test_large_additions_delegate_to_existing_selector(op,monkeypatch):
    from hermax.encoder._integer_sum import selection
    calls=[]
    original=selection.choose
    def record(*args,**kwargs):
        calls.append(True)
        return original(*args,**kwargs)
    monkeypatch.setattr(selection,'choose',record)
    m=Model();x=m.int('x',0,1000);y=m.int('y',0,1000);z=m.int('z',0,2000)
    m &= (x+y==z) if op=='==' else (x+y<=z)
    assert calls


@pytest.mark.parametrize('equality',[False,True])
def test_static_output_bound_keeps_input_bound_propagation(equality):
    m=Model();x=m.int('x',0,30);y=m.int('y',0,30);z=m.int('z',0,30)
    m &= (x+y==z) if equality else (x+y<=z)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        ok,forced=solver.propagate(assumptions=[m._lit_to_dimacs(x>=20)])
        assert ok
        assert m._lit_to_dimacs(y<=10) in forced
