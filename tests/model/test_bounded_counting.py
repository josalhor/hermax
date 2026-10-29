import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model.encoders import _EncoderDispatch as Dispatch


@pytest.mark.parametrize('signed', [False, True])
def test_requested_thresholds_match_full_counter_soundness_and_propagation(signed):
    builds=[]
    for bounded in (False, True):
        m=Model();bits=list(m.bool_vector('b',5))
        if signed: bits=[bits[0],~bits[1],bits[2],bits[0],bits[4]]
        kwargs={'thresholds': [2,3]} if bounded else {}
        clauses,outputs=Dispatch._build_sequential_ge_counter(m,bits,**kwargs)
        m._hard.extend(clauses);cnf=m.to_cnf()
        builds.append((Solver(name='g4',bootstrap_with=cnf.clauses),[m._lit_to_dimacs(outputs[k]) for k in (2,3)]))
    try:
        for values in itertools.product((False,True),repeat=5):
            count=sum((not values[1] if i==1 else values[0] if i==3 else values[i])
                      if signed else values[i] for i in range(5))
            inputs=[i+1 if v else -i-1 for i,v in enumerate(values)]
            for solver,outs in builds:
                assert solver.solve(assumptions=inputs+[outs[0] if count>=2 else -outs[0],outs[1] if count>=3 else -outs[1]])
                assert not solver.solve(assumptions=inputs+[outs[0] if count<2 else -outs[0]])
        for values in itertools.product((None,False,True),repeat=7):
            observed=[]
            for solver,outs in builds:
                ids=list(range(1,6))+outs
                assumptions=[lit if v else -lit for lit,v in zip(ids,values) if v is not None]
                ok,forced=solver.propagate(assumptions=assumptions)
                observed.append((ok, frozenset((i,v) for i,lit in enumerate(ids) for v in (False,True)
                                               if (lit if v else -lit) in forced) if ok else frozenset()))
            assert observed[0]==observed[1]
    finally:
        for solver,_ in builds:solver.delete()


@pytest.mark.parametrize('thresholds', [(2, 3, 4), (253, 254, 255)])
def test_small_threshold_omits_unused_counter_work(thresholds):
    m=Model();bits=list(m.bool_vector('b',256))
    clauses,_=Dispatch._build_sequential_ge_counter(m,bits,thresholds=thresholds)
    assert len(clauses)<7000


def test_guarded_at_most_one_avoids_quadratic_pairwise_expansion():
    from hermax.model.expressions import sum_expr
    m=Model();bits=m.bool_vector('b',512);gate=m.bool('g')
    m &= sum_expr(bits)<=1+512*gate
    assert len(m.to_cnf().clauses)<3000


def test_complementary_inputs_and_unused_outputs():
    m=Model();a=m.bool('a')
    clauses,outputs=Dispatch._build_sequential_ge_counter(m,[a,~a],thresholds=[1,2])
    assert clauses==[]
    assert outputs=={1:True,2:False}
    assert Dispatch._build_sequential_ge_counter(m,[a],thresholds=[])==([], {})


@pytest.mark.parametrize('coefficient', [-2,1,3])
@pytest.mark.parametrize('op', ['<=','>='])
@pytest.mark.parametrize('bound', [1,3,6])
def test_mixed_counter_branches_match_independent_arithmetic(coefficient,op,bound):
    from hermax.model.expressions import sum_expr
    m=Model();bits=list(m.bool_vector('b',5));g=m.bool('g');x=m.int('x',0,3)
    expr=coefficient*x+sum_expr(bits)
    m &= (expr<=bound+g) if op=='<=' else (expr>=bound+g)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        cuts=[m._lit_to_dimacs(x>=k) for k in range(1,4)]
        for values,xv,gv in itertools.product(itertools.product((False,True),repeat=5),range(4),(False,True)):
            assumptions=[m._lit_to_dimacs(lit if v else ~lit) for lit,v in zip(bits,values)]
            assumptions.append(g.id if gv else -g.id)
            assumptions.extend(lit if xv>=k else -lit for k,lit in enumerate(cuts,1))
            lhs=coefficient*xv+sum(values)
            expected=lhs<=bound+gv if op=='<=' else lhs>=bound+gv
            assert solver.solve(assumptions=assumptions)==expected


@pytest.mark.parametrize("signed", [False, True])
def test_high_count_thresholds_preserve_exact_values(signed):
    model = Model()
    bits = list(model.bool_vector("b", 5))
    inputs = [bits[0], ~bits[1], bits[2], bits[0], bits[4]] if signed else bits
    clauses, outputs = Dispatch._build_sequential_ge_counter(
        model, inputs, thresholds=[4, 5]
    )
    model._hard.extend(clauses)
    with Solver(bootstrap_with=model.to_cnf().clauses) as solver:
        for values in itertools.product([False, True], repeat=5):
            count = (2 * values[0] + (not values[1]) + values[2] + values[4]
                     if signed else sum(values))
            fixed = [model._lit_to_dimacs(lit if value else ~lit)
                     for lit, value in zip(bits, values)]
            for states in itertools.product([False, True], repeat=2):
                expected = states == (count >= 4, count >= 5)
                conditions = [model._lit_to_dimacs(outputs[rank] if state else ~outputs[rank])
                              for rank, state in zip([4, 5], states)]
                assert solver.solve(assumptions=fixed + conditions) is expected


def test_ordered_sum_retains_backward_propagation():
    model = Model()
    a, b = model.int("a", 0, 2), model.int("b", 0, 3)
    clauses, outputs = Dispatch._build_unary_sum_ge_ladder(
        model, a._threshold_lits, b._threshold_lits, thresholds=[4]
    )
    model._hard.extend(clauses)
    with Solver(bootstrap_with=model.to_cnf().clauses) as solver:
        # b == 2 and a + b < 4 must propagate a < 2.
        fixed = [model._lit_to_dimacs(b >= 2), model._lit_to_dimacs(b < 3),
                 model._lit_to_dimacs(~outputs[4])]
        ok, forced = solver.propagate(assumptions=fixed)
        assert ok and model._lit_to_dimacs(a < 2) in forced
