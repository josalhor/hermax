import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model


def test_reified_lex_shares_one_suffix_circuit():
    m=Model();left=m.int_vector('left',16,0,100);right=m.int_vector('right',16,0,100);flag=m.bool('flag')
    before=len(m.to_cnf().clauses)
    m &= left.lexicographic_less_than(right).iff(flag)
    cnf=m.to_cnf()
    assert len(cnf.clauses)-before<7000
    assert cnf.nv-3201<=16


@pytest.mark.parametrize('mode',['post','iff','gated_iff','implies'])
def test_lex_suffix_matches_different_integer_domains(mode):
    m=Model();left=m.int_vector('left',2,-1,1);right=m.int_vector('right',2,0,2)
    flag,gate=m.bool('flag'),m.bool('gate')
    comparison=left.lexicographic_less_than(right)
    if mode=='gated_iff':comparison=comparison.only_if(gate)
    m &= comparison if mode=='post' else comparison.implies(flag) if mode=='implies' else comparison.iff(flag)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for av,bv,on,gv in itertools.product(itertools.product(range(-1,2),repeat=2),itertools.product(range(3),repeat=2),(False,True),(False,True)):
            assumptions=[]
            for vector,values in ((left,av),(right,bv)):
                for variable,value in zip(vector,values):
                    assumptions.extend(m._lit_to_dimacs(variable>=k) if value>=k else -m._lit_to_dimacs(variable>=k) for k in range(variable.lb+1,variable.ub+1))
            assumptions.extend([flag.id if on else -flag.id,gate.id if gv else -gate.id])
            truth=av<bv
            expected=truth if mode=='post' else (not truth or on) if mode=='implies' else on==((not gv or truth) if mode=='gated_iff' else truth)
            assert solver.solve(assumptions=assumptions)==expected


def test_impossible_suffix_forces_strict_first_comparison():
    m=Model();left=m.int_vector('left',2,0,10);right=m.int_vector('right',2,0,10)
    m &= left.lexicographic_less_than(right)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        assumptions=[m._lit_to_dimacs(left[0]>=4),m._lit_to_dimacs(left[1]>=7),m._lit_to_dimacs(right[1]<=6)]
        ok,forced=solver.propagate(assumptions=assumptions)
        assert ok
        assert m._lit_to_dimacs(right[0]>=5) in forced


def test_repeated_reification_reuses_suffix_definition():
    m=Model();left=m.int_vector('left',4,0,5);right=m.int_vector('right',4,0,5)
    first,second=m.bool('first'),m.bool('second')
    comparison=left.lexicographic_less_than(right)
    m &= comparison.iff(first)
    before=m._top_id(),len(m.to_cnf().clauses)
    m &= comparison.iff(second)
    after=m._top_id(),len(m.to_cnf().clauses)
    assert after[0]==before[0]
    assert after[1]==before[1]+2
