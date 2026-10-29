import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model import _integer_sum as sums


@pytest.mark.parametrize('choices,expected',[(('binary','binary'),['==']), (('whole','whole'),[]), (('binary','whole'),['<=']), (('whole','binary'),['>='])])
def test_equality_shares_only_two_binary_selections(monkeypatch,choices,expected):
    calls=[];iterator=iter(choices)
    monkeypatch.setattr(sums.selection,'choose',lambda *a,**kw:next(iterator))
    original=sums.binary_pb
    def record(views,coefficients,bound,comparator,top_id):
        calls.append(comparator)
        return original(views,coefficients,bound,comparator,top_id)
    monkeypatch.setattr(sums,'binary_pb',record)
    m=Model();xs=[m.int(f'x{i}',0,3) for i in range(4)]
    m &= sums.compile_sum(m,list(zip(xs,[1,-1,1,-1])),-1,'==')
    assert calls==expected
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(range(4),repeat=4):
            assumptions=[m._lit_to_dimacs(x>=k) if v>=k else -m._lit_to_dimacs(x>=k)
                         for x,v in zip(xs,values) for k in range(1,4)]
            assert solver.solve(assumptions=assumptions)==(values[0]-values[1]+values[2]-values[3]==1)


def test_native_equality_saves_auxiliaries(monkeypatch):
    monkeypatch.setattr(sums.selection,'choose',lambda *a,**kw:'binary')
    sizes=[]
    for split in (False,True):
        m=Model();xs=[m.int(f'x{i}',0,100) for i in range(8)];items=list(zip(xs,[1]*8))
        if split:
            m &= sums.compile_sum(m,items,-400,'<=') & sums.compile_sum(m,items,-400,'>=')
        else:m &= sums.compile_sum(m,items,-400,'==')
        c=m.to_cnf();sizes.append((c.nv,len(c.clauses)))
    assert all(a<b for a,b in zip(sizes[0],sizes[1]))


def test_shared_equality_remains_sound_when_guarded_and_reified(monkeypatch):
    monkeypatch.setattr(sums.selection,'choose',lambda *a,**kw:'binary')
    m=Model();xs=[m.int(f'x{i}',-1,1) for i in range(4)]
    gate,indicator=m.bool('gate'),m.bool('indicator')
    from hermax.model.expressions import sum_expr
    m &= (sum_expr(xs)==0).only_if(gate).iff(indicator)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for values,gv,bv in itertools.product(itertools.product(range(-1,2),repeat=4),(False,True),(False,True)):
            assumptions=[m._lit_to_dimacs(x>=k) if v>=k else -m._lit_to_dimacs(x>=k)
                         for x,v in zip(xs,values) for k in (0,1)]
            assumptions.extend([gate.id if gv else -gate.id,indicator.id if bv else -indicator.id])
            assert solver.solve(assumptions=assumptions)==(bv==(not gv or sum(values)==0))
