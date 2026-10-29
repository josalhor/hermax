import pytest
from hermax.internal import _integer_sum_native as native
from hermax.internal._clause_storage import ClauseStorage


@pytest.mark.parametrize('mode',[0,1])
@pytest.mark.parametrize('bound',[-1,0,3,7,12])
def test_order_sum_packed_matches_public_output(mode,bound):
    args=([[1,2,3],[-4,-5],[6,7,8,9]],bound,20,mode,0)
    plain,nv=native.encode_order_sum(*args)
    raw,packed_nv=native._encode_order_sum_packed(*args)
    assert type(plain) is list
    assert ClauseStorage._wrap(raw).to_lists()==plain
    assert packed_nv==nv


@pytest.mark.parametrize('encoder',[0,1,2,3,4,5,7])
@pytest.mark.parametrize('comparator',[native.LEQ,native.GEQ,native.BOTH])
def test_budgeted_pb_packed_matches_public_output(encoder,comparator):
    kwargs=dict(wlits=[(1,3),(-2,5),(3,7),(4,11)],comparator=comparator,bound=13,
                top_id=20,pb_encoder=encoder,conditionals=[6,-7],state_limit=20000,clause_limit=50000)
    plain,nv=native.encode_pb(**kwargs)
    raw,packed_nv=native._encode_pb_packed(**kwargs)
    assert type(plain) is list
    assert ClauseStorage._wrap(raw).to_lists()==plain
    assert packed_nv==nv


@pytest.mark.parametrize('binding',['encode_pb','_encode_pb_packed'])
def test_clause_budget_remains_enforced(binding):
    with pytest.raises(native.EncodingBudgetExceeded,match='clauses'):
        getattr(native,binding)([(i, i+1) for i in range(1,20)],native.LEQ,40,30,1,[],0,1)


def test_model_integer_encoders_do_not_use_list_returning_bindings(monkeypatch):
    from hermax.model import Model
    from hermax.model.expressions import sum_expr
    from hermax.encoder._integer_sum import selection

    def forbidden(*args,**kwargs):
        raise AssertionError('model used list-returning native output')

    monkeypatch.setattr(native,'encode_order_sum',forbidden)
    monkeypatch.setattr(native,'encode_pb',forbidden)
    monkeypatch.setattr(selection,'choose',lambda *args,**kwargs:'whole')
    m=Model();xs=[m.int(f'x{i}',0,3) for i in range(4)]
    m &= sum_expr(xs)<=6
    m &= sum_expr(c*x for c,x in zip((2,3,5,7),xs))<=15
    assert m.solve().ok


def test_packed_native_output_survives_producer_and_snapshot_mutation():
    raw,_=native._encode_order_sum_packed([[1,2,3],[4,5,6]],3,10,1,0)
    output=ClauseStorage._wrap(raw)
    expected=output.to_lists()
    saved=ClauseStorage(output)
    del raw
    output.append([])
    del output
    assert saved.to_lists()==expected
