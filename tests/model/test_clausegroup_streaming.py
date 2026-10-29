import itertools
import pytest
from hermax.model import Model,Clause,ClauseGroup
import hermax.model.expressions as expressions


def test_existing_clause_tuples_are_streamed_without_copying(monkeypatch):
    m=Model();a,b=m.bool('a'),m.bool('b');clause=Clause(m,[a,~b])
    original=expressions._ClauseStorage
    seen=[]
    def storage(rows):
        assert not isinstance(rows,(list,tuple))
        iterator=iter(rows);first=next(iterator)
        assert first is clause.dimacs
        seen.append(True)
        return original(itertools.chain([first],iterator))
    monkeypatch.setattr(expressions,'_ClauseStorage',storage)
    group=ClauseGroup(m,[clause,Clause(m,[])])
    assert seen
    assert list(group)==[clause.dimacs,()]


@pytest.mark.parametrize('bad',[True,0,1.5,'1'])
def test_raw_clause_validation_is_preserved(bad):
    with pytest.raises((TypeError,ValueError)):
        ClauseGroup(Model(),[[bad]])


def test_foreign_clause_is_still_rejected():
    owner,other=Model(),Model()
    with pytest.raises(ValueError):
        ClauseGroup(other,[Clause(owner,[owner.bool('x')])])


@pytest.mark.parametrize('reserve',[False,True])
def test_raw_rows_reserve_ids_and_snapshot_input(reserve):
    m=Model();rows=[[17,-19],[]]
    group=ClauseGroup(m,iter(rows),reserve_aux_ids=reserve)
    rows[0][0]=100
    assert list(group)==[(17,-19),()]
    assert m.bool('after').id==(20 if reserve else 1)
