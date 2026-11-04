import itertools
import pytest
from hermax.model import Model
from pysat.solvers import Solver


@pytest.mark.parametrize('kind', ['except', 'precedence', 'regular', 'mdd', 'no_overlap'])
def test_native_globals_projection_and_conditional_posting(kind):
    m = Model()
    xs = [m.int('x'+str(i), 0, 2) for i in range(3)]
    if kind == 'except':
        c = m.all_different_except(xs)
        oracle = lambda a: len([v for v in a if v]) == len(set(v for v in a if v))
    elif kind == 'precedence':
        c = m.precedence(xs, [0,1,2])
        oracle = lambda a: all(v != b or s in a[:i] for s,b in [(0,1),(1,2)] for i,v in enumerate(a))
    elif kind == 'regular':
        c = m.regular(xs, [(s,v,(s+v)%2) for s in range(2) for v in range(3)], 0, [0])
        oracle = lambda a: sum(a)%2 == 0
    elif kind == 'mdd':
        c = m.mdd(xs, [('r',0,'a'),('r',1,'a'),('a',2,'b'),('b',1,'z')], 'r')
        oracle = lambda a: a in [(0,2,1),(1,2,1)]
    else:
        c = m.no_overlap(xs, [0,1,2])
        oracle = lambda a: a[1]+1 <= a[2] or a[2]+2 <= a[1]
    # Building a constraint must leave it unenforced until posted.
    atoms = [[m._lit_to_dimacs(x==v) for v in range(3)] for x in xs]
    with Solver(name='g3', bootstrap_with=m.to_cnf().clauses) as sat:
        for a in itertools.product(range(3), repeat=3):
            assert sat.solve(assumptions=[atoms[i][v] for i,v in enumerate(a)])
    gate = m.bool()
    m &= c.only_if(gate)
    lit = m._lit_to_dimacs(gate)
    with Solver(name='g3', bootstrap_with=m.to_cnf().clauses) as sat:
        for a in itertools.product(range(3), repeat=3):
            assumptions = [atoms[i][v] for i,v in enumerate(a)]
            assert sat.solve(assumptions=assumptions+[lit]) == oracle(a)
            assert sat.solve(assumptions=assumptions+[-lit])


def test_regular_single_state_repeated_construction():
    m = Model()
    xs = [m.int('x',0,2)]*3
    m &= m.regular(xs, [('s',1,'s')], 's', ['s'])
    m &= m.regular(xs, [('s',1,'s')], 's', ['s'])
    assert m.solve().ok

@pytest.mark.parametrize('kind', ['membership','equal_except','lex_le'])
def test_more_globals_projection(kind):
    m = Model()
    xs = [m.int('v'+str(i),0,2) for i in range(4)]
    if kind == 'membership':
        c = xs[0].is_in([-5,0,2,2,100])
        oracle = lambda a: a[0] in [0,2]
    elif kind == 'equal_except':
        c = m.all_equal_except(xs,[0])
        oracle = lambda a: len(set(a)-{0}) <= 1
    else:
        c = m.vector(xs[:2]).lexicographic_less_or_equal(m.vector(xs[2:]))
        oracle = lambda a: a[:2] <= a[2:]
    atoms = [[m._lit_to_dimacs(x==v) for v in range(3)] for x in xs]
    gate = m.bool()
    m &= c.only_if(gate)
    lit = m._lit_to_dimacs(gate)
    with Solver(name='g3', bootstrap_with=m.to_cnf().clauses) as sat:
        for a in itertools.product(range(3),repeat=4):
            assumptions = [atoms[i][v] for i,v in enumerate(a)]
            assert sat.solve(assumptions=assumptions+[lit]) == oracle(a)
            assert sat.solve(assumptions=assumptions+[-lit])


def test_membership_empty_and_full_reification():
    m = Model()
    x = m.int('x',0,2)
    for values, truth in [([],False), ([-1,0,1,2,3],True)]:
        b = m.bool()
        m &= x.is_in(values).iff(b)
        lit = m._lit_to_dimacs(b)
        with Solver(name='g3', bootstrap_with=m.to_cnf().clauses) as sat:
            assert sat.solve(assumptions=[lit if truth else -lit])
            assert not sat.solve(assumptions=[-lit if truth else lit])
