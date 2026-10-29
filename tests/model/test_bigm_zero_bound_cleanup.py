import itertools
import pytest
from pysat.solvers import Solver
from hermax.model import Model
from hermax.model.expressions import sum_expr


@pytest.mark.parametrize('strict',[False,True])
@pytest.mark.parametrize('weighted',[False,True])
def test_zero_bound_uses_direct_units_without_cardinality_encoding(monkeypatch,strict,weighted):
    import hermax.model.encoders as encoders
    def forbidden(*args,**kwargs):
        raise AssertionError('zero bound reached a cardinality encoder')
    monkeypatch.setattr(encoders._EncoderDispatch,'_compile_structured_auto_leq',staticmethod(forbidden))
    m=Model();bits=list(m.bool_vector('b',4))
    expr=sum_expr((i+1 if weighted else 1)*bit for i,bit in enumerate(bits))+7
    m &= (expr<8) if strict else (expr<=7)
    assert len(m.to_cnf().clauses)==4
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product((False,True),repeat=4):
            assumptions=[bit.id if value else -bit.id for bit,value in zip(bits,values)]
            assert solver.solve(assumptions=assumptions)==(not any(values))
