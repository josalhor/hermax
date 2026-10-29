import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model.variables import EnumVector


def test_explicit_nullable_bipartite_does_not_fall_back_to_pairwise(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('explicit bipartite request fell back to pairwise')
    monkeypatch.setattr(EnumVector,'_all_different_pairwise',forbidden)
    m=Model();items=m.enum_vector('e',8,list(range(16)),nullable=True)
    m &= items.all_different(backend='bipartite')
    assert m.solve().ok


def test_auto_nullable_retains_pairwise_encoding():
    sizes=[]
    for backend in ('auto','pairwise'):
        m=Model();items=m.enum_vector('e',4,['a','b','c'],nullable=True)
        m &= items.all_different(backend=backend)
        c=m.to_cnf();sizes.append((c.clauses,c.nv))
    assert sizes[0]==sizes[1]


@pytest.mark.parametrize('nullable',[(True,True,True),(True,False,True),(False,False,False)])
@pytest.mark.parametrize('mode',['post','iff','gated_iff'])
def test_nullable_columns_match_values_and_reification(nullable,mode):
    m=Model();items=[m.enum(f'e{i}',['a','b'],nullable=flag) for i,flag in enumerate(nullable)]
    vector=m.vector(items);r,g=m.bool('r'),m.bool('g')
    condition=vector.all_different(backend='bipartite')
    if mode=='gated_iff':condition=condition.only_if(g)
    m &= condition if mode=='post' else condition.iff(r)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        domains=[['a','b',None] if flag else ['a','b'] for flag in nullable]
        for values,rv,gv in itertools.product(itertools.product(*domains),(False,True),(False,True)):
            truth=len(set(values))==len(values)
            expected=truth if mode=='post' else rv==((not gv or truth) if mode=='gated_iff' else truth)
            assumptions=[lit.id if choice==value else -lit.id for item,value in zip(items,values) for choice,lit in item._choice_lits.items()]
            assumptions.extend([r.id if rv else -r.id,g.id if gv else -g.id])
            assert solver.solve(assumptions=assumptions)==expected


@pytest.mark.parametrize('size',[0,1,2])
def test_none_only_enums_keep_all_different_semantics(size):
    m=Model();items=m.enum_vector('e',size,[],nullable=True);flag=m.bool('r')
    m &= items.all_different(backend='bipartite').iff(flag)
    assert m.solve(assumptions=[flag if size<=1 else ~flag]).ok
    assert not m.solve(assumptions=[~flag if size<=1 else flag]).ok


def test_none_indicator_is_shared_with_tables():
    m=Model();items=m.enum_vector('e',3,['a','b'],nullable=True)
    original=m._table_enum_none_atom(items[0])
    m &= items.all_different(backend='bipartite')
    before=m._top_id()
    assert items[0]._none_indicator() is original
    assert m._table_enum_none_atom(items[0]) is original
    assert m._top_id()==before
