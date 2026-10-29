import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model._cumulative import _CumulativeEncoding


def test_task_events_are_distinct_and_skip_large_gaps():
    m=Model();starts=[m.int(f's{i}',lo,hi) for i,(lo,hi) in enumerate([(-3,0),(-1,2),(1000000,1000001)])]
    encoding=_CumulativeEncoding(m,tuple((s,2,1) for s in starts),2,'task')
    assert list(encoding._events())==list(range(-3,3))+[1000000,1000001]


def test_shared_windows_do_not_repeat_capacity_encodings():
    m=Model();starts=[m.int(f's{i}',i%2*10000,i%2*10000+10) for i in range(32)]
    before=len(m.to_cnf().clauses)
    m &= m.cumulative(starts,[3]*32,[1]*32,8)
    assert len(m.to_cnf().clauses)-before<5000
    assert m.solve().ok


@pytest.mark.parametrize('mode',['post','iff','gated_iff'])
@pytest.mark.parametrize('durations,demands,capacity',[([2,3,2],[1,2,1],2),([1,2,3],[2,1,2],3)])
def test_shared_events_match_time_loads(mode,durations,demands,capacity):
    m=Model();lower=[-1,0,10];starts=[m.int(f's{i}',lo,lo+2) for i,lo in enumerate(lower)]
    gate,indicator=m.bool('g'),m.bool('r')
    condition=m.cumulative(starts,durations,demands,capacity,backend='task')
    if mode=='gated_iff':condition=condition.only_if(gate)
    m &= condition if mode=='post' else condition.iff(indicator)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for values,gv,rv in itertools.product(itertools.product(range(3),repeat=3),(False,True),(False,True)):
            actual=[v+lo for v,lo in zip(values,lower)]
            valid=all(sum(d for s,duration,d in zip(actual,durations,demands) if s<=t<s+duration)<=capacity for t in range(-1,16))
            expected=valid if mode=='post' else rv==((not gv or valid) if mode=='gated_iff' else valid)
            assumptions=[]
            for s,value in zip(starts,actual):
                assumptions.extend(m._lit_to_dimacs(s>=k) if value>=k else -m._lit_to_dimacs(s>=k) for k in range(s.lb+1,s.ub+1))
            assumptions.extend([gate.id if gv else -gate.id,indicator.id if rv else -indicator.id])
            assert solver.solve(assumptions=assumptions)==expected


def test_shared_overload_events_propagate_reified_result():
    m=Model();starts=[m.int(f's{i}',0,2) for i in range(2)];indicator=m.bool('r')
    m &= m.cumulative(starts,[2,2],[1,1],1,backend='task').iff(indicator)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        assumptions=[m._lit_to_dimacs(s<=0) for s in starts]
        ok,forced=solver.propagate(assumptions=assumptions)
        assert ok
        assert -indicator.id in forced
