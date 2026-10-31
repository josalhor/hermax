import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model.expressions import sum_expr
from hermax.model.encoders import _EncoderDispatch
from hermax.encoder._cardinality_policy import reified_equality_lower_bound


@pytest.mark.parametrize('n,bound,max_vars,max_clauses', [
    (32, 16, 350, 900), (1000, 3, 6500, 17000),
])
def test_reified_equality_shares_both_directions_when_smaller(n, bound, max_vars, max_clauses):
    model = Model()
    bits = model.bool_vector('b', n)
    flag = model.bool('r')
    model &= (sum_expr(bits) == bound).iff(flag)
    cnf = model.to_cnf()
    assert cnf.nv <= max_vars
    assert len(cnf.clauses) <= max_clauses


@pytest.mark.parametrize('n,bound', [(4, 2), (200, 100)])
def test_larger_shared_counter_is_not_built(monkeypatch, n, bound):
    def reject(*args, **kwargs):
        pytest.fail('shared counter should have been rejected before construction')

    monkeypatch.setattr(_EncoderDispatch, '_build_sequential_ge_counter', reject)
    model = Model()
    bits = model.bool_vector('b', n)
    flag = model.bool('r')
    model &= (sum_expr(bits) == bound).iff(flag)
    model.to_cnf()


@pytest.mark.parametrize('context', ['complementary', 'indicator_input', 'known_amo'])
def test_contexts_outside_the_size_guarantee_keep_fallback(monkeypatch, context):
    def reject(*args, **kwargs):
        pytest.fail('shared counter was selected outside its size guarantee')

    monkeypatch.setattr(_EncoderDispatch, '_build_sequential_ge_counter', reject)
    model = Model()
    bits = list(model.bool_vector('b', 8))
    flag = bits[0] if context == 'indicator_input' else model.bool('r')
    if context == 'complementary':
        bits = [bits[0], ~bits[0], *bits[1:7]]
    if context == 'known_amo':
        model &= model.bool_vector('other', 2).at_most_one()
    model &= (sum_expr(bits) == 3).iff(flag)
    model.to_cnf()


@pytest.mark.parametrize('bound', [3, 4, 5])
@pytest.mark.parametrize('negative_flag', [False, True])
@pytest.mark.parametrize('gated', [False, True])
def test_shared_equality_matches_arithmetic_in_both_directions(bound, negative_flag, gated):
    model = Model()
    bits = list(model.bool_vector('b', 8))
    inputs = [~bit if i % 2 else bit for i, bit in enumerate(bits)]
    flag = model.bool('r')
    gate = model.bool('gate')
    indicator = ~flag if negative_flag else flag
    condition = sum_expr(inputs, start=2) == bound + 2
    if gated:
        condition = condition.only_if(gate)
    model &= condition.iff(indicator)
    with Solver(bootstrap_with=model.to_cnf().clauses) as solver:
        for values in itertools.product([False, True], repeat=8):
            count = sum(not value if i % 2 else value for i, value in enumerate(values))
            fixed = [bit.id if value else -bit.id for bit, value in zip(bits, values)]
            for rv, gv in itertools.product([False, True], repeat=2):
                truth = (not gv or count == bound) if gated else count == bound
                expected = (not rv if negative_flag else rv) == truth
                assumptions = fixed + [flag.id if rv else -flag.id, gate.id if gv else -gate.id]
                assert solver.solve(assumptions=assumptions) == expected


def test_reification_lower_bound_does_not_overestimate_fallback(monkeypatch):
    monkeypatch.setattr(_EncoderDispatch, '_can_share_reified_count', lambda *args: False)
    for n in [4, 8, 13, 32, 65]:
        for bound in {b for b in (2, 3, n // 2, n - 3, n - 2) if 2 <= b <= n - 2}:
            model = Model()
            bits = model.bool_vector('b', n)
            flag = model.bool('r')
            model &= (sum_expr(bits) == bound).iff(flag)
            cnf = model.to_cnf()
            variables, clauses = reified_equality_lower_bound(n, bound)
            assert variables <= cnf.nv - n - 1
            assert clauses <= len(cnf.clauses)


def test_shared_equality_preserves_input_and_indicator_propagation(monkeypatch):
    original = _EncoderDispatch._can_share_reified_count
    solvers = []
    for choose in [lambda *args: False, original]:
        monkeypatch.setattr(_EncoderDispatch, '_can_share_reified_count', staticmethod(choose))
        model = Model()
        bits = model.bool_vector('b', 8)
        flag = model.bool('r')
        model &= (sum_expr(bits) == 3).iff(flag)
        solvers.append(Solver(bootstrap_with=model.to_cnf().clauses))
    try:
        visible = set(range(1, 10)) | set(range(-9, 0))
        for values in itertools.product([None, False, True], repeat=9):
            fixed = [i if value else -i for i, value in enumerate(values, 1) if value is not None]
            old_ok, old_forced = solvers[0].propagate(assumptions=fixed)
            new_ok, new_forced = solvers[1].propagate(assumptions=fixed)
            true = values[:8].count(True)
            unknown = values[:8].count(None)
            feasible = (true <= 3 <= true + unknown if values[8] is True else
                        (unknown > 0 or true != 3) if values[8] is False else True)
            assert new_ok == feasible
            assert not new_ok or old_ok and (set(old_forced) & visible) <= set(new_forced)
    finally:
        for solver in solvers:
            solver.delete()


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
