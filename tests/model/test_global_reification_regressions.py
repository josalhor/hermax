import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model

@pytest.mark.parametrize('kind',['equal','different','regular','precedence','mdd'])
@pytest.mark.parametrize('binary',[False,True])
def test_global_full_reification(kind,binary):
    m=Model();m.set_integer_binary_threshold(2 if binary else None)
    xs=[m.int('x'+str(i),0,2) for i in range(2)]
    if kind=='equal':
        c=m.all_equal_except(xs,[0,99]);oracle=lambda a:len(set(a)-{0})<=1
    elif kind=='different':
        c=m.all_different_except(xs,[0,99]);oracle=lambda a:a[0]!=a[1] or a[0]==0
    elif kind=='regular':
        c=m.regular(xs,[(s,v,(s+v)%2) for s in range(2) for v in range(3)],0,[0]);oracle=lambda a:sum(a)%2==0
    elif kind=='precedence':
        c=m.precedence(xs,[0,1]);oracle=lambda a:all(v!=1 or 0 in a[:i] for i,v in enumerate(a))
    else:
        c=m.mdd(xs,[('r',0,'a'),('r',1,'a'),('a',2,'z')],'r');oracle=lambda a:a[0] in (0,1) and a[1]==2
    flag=m.bool();m &= c.iff(flag)
    atoms=[{v:[m._lit_to_dimacs(a) for a in x._exact_value_atoms(v)] for v in range(3)} for x in xs]
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(range(3),repeat=2):
            fixed=[a for lookup,v in zip(atoms,values) for a in lookup[v]]
            for f in (False,True):
                assert solver.solve(assumptions=fixed+[flag.id if f else -flag.id]) == (f==oracle(values)),(kind,values,f)

@pytest.mark.parametrize('kind', ['equal','different','regular'])
def test_global_negation_under_gate(kind):
    m=Model();x=m.int('x',0,0);y=m.int('y',0,0)
    if kind=='equal': c=m.all_equal_except([x,y])
    elif kind=='different': c=m.all_different_except([x,y])
    else: c=m.regular([x,y],[(0,0,0)],0,[0])
    flag,gate=m.bool(),m.bool()
    m &= c.only_if(gate).iff(flag)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        assert not solver.solve(assumptions=[gate.id,-flag.id])
        assert not solver.solve(assumptions=[-gate.id,-flag.id])
        assert solver.solve(assumptions=[gate.id,flag.id])


def test_regular_nondeterministic_paths_and_unposted_constraint():
    m=Model();x=m.int('x',0,1)
    c=m.regular([x],[(0,0,1),(0,0,2),(0,1,1)],0,[2])
    m &= x==1
    assert m.solve().ok
    m &= c
    assert m.solve().status=='unsat'


@pytest.mark.parametrize('kind',['equal','different'])
def test_exclusions_outside_every_domain(kind):
    m=Model();xs=[m.int('a',1,2),m.int('b',1,2)]
    c=(m.all_equal_except if kind=='equal' else m.all_different_except)(xs,[99])
    m &= c
    m &= xs[0]==1
    m &= xs[1]==(1 if kind=='equal' else 2)
    assert m.solve().ok


@pytest.mark.parametrize("first, expected", [(1, True), (0, False)])
def test_precedence_with_labels_missing_from_individual_domains(first, expected):
    model = Model()
    x = model.int("x", 0, 1)
    y = model.int("y", 2, 3)
    z = model.int("z", 4, 4)
    flag = model.bool("flag")
    model &= model.precedence([x, y, z], [1, 4]).iff(flag)
    model &= x == first

    assert model.solve(assumptions=[flag if expected else ~flag]).status == "sat"
    assert model.solve(assumptions=[~flag if expected else flag]).status == "unsat"
