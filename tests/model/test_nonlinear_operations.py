import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import AbsExpr, Model, PBExpr


def atoms(m, x, value):
    return [m._lit_to_dimacs(lit) for lit in x._exact_value_atoms(value)]


@pytest.mark.parametrize('threshold', [None, 2, 64])
@pytest.mark.parametrize('left,right', [((0,3),(0,3)), ((-3,3),(-2,4)),
                                       ((3,7),(11,17)), ((-5,5),(-4,4)),
                                       ((0,15),(0,15))])
def test_product_matches_all_input_assignments(threshold, left, right):
    m = Model(); m.set_integer_binary_threshold(threshold)
    x,y = m.int('x',*left),m.int('y',*right)
    z = m.product(x,y)
    with Solver(name='g4', bootstrap_with=m.to_cnf().clauses) as solver:
        for a,b in itertools.product(range(x.lb,x.ub+1),range(y.lb,y.ub+1)):
            inputs = atoms(m,x,a)+atoms(m,y,b)
            output = atoms(m,z,a*b)
            assert solver.solve(assumptions=inputs+output)
            for bit in output:
                assert not solver.solve(assumptions=inputs+[-bit])


@pytest.mark.parametrize('threshold',[None,2,64])
@pytest.mark.parametrize('domain',[(-5,-2),(-2,3),(3,8),(0,127),(100,170)])
@pytest.mark.parametrize('negated',[False,True])
def test_boolean_products_are_exact_with_signed_and_shifted_domains(threshold,domain,negated):
    m=Model();m.set_integer_binary_threshold(threshold)
    bit=m.bool('b');control=~bit if negated else bit
    x=m.int('x',*domain);z=m.product(control,x)
    assert m.product(x,control) is z
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for flag,value in itertools.product([False,True],range(x.lb,x.ub+1)):
            inputs=[m._lit_to_dimacs(control) if flag else -m._lit_to_dimacs(control)]+atoms(m,x,value)
            out=atoms(m,z,value if flag else 0)
            assert solver.solve(assumptions=inputs+out)
            for atom in out:assert not solver.solve(assumptions=inputs+[-atom])


def test_wide_product_uses_logarithmic_domains_and_handles_negative_offsets():
    m=Model();x=m.int('x',-10**6,10**6);y=m.int('y',0,10**6)
    z=m.product(x,y)
    cnf=m.to_cnf()
    assert cnf.nv<20000 and len(cnf.clauses)<100000
    with Solver(name='g4',bootstrap_with=cnf.clauses) as solver:
        for a,b in [(-10**6,10**6),(-12345,67890),(0,1),(10**6,10**6)]:
            inputs=atoms(m,x,a)+atoms(m,y,b)
            out=atoms(m,z,a*b)
            assert solver.solve(assumptions=inputs+out)
            assert not solver.solve(assumptions=inputs+[-out[0]])


def test_boolean_products_fold_and_direct_masks_need_no_arithmetic_helpers():
    m=Model();bit=m.bool('b');x=m.int('x',0,100)
    assert m.product(bit,bit) is m.as_int(bit)
    zero=m.product(bit,~bit);assert zero.lb==zero.ub==0
    before=m.to_cnf()
    z=m.product(bit,x)
    after=m.to_cnf()
    assert after.nv-before.nv==len(x._binary_view)
    assert len(after.clauses)-len(before.clauses)==25  # Seven ANDs plus domain cuts.
    m &= bit;m &= x==87
    result=m.solve();assert result.ok and result[z]==87


@pytest.mark.parametrize('domain',[(-7,7),(-4,-1),(2,6),(0,31),(0,100)])
def test_squares_have_correct_bounds_and_values(domain):
    m=Model();x=m.int('x',*domain);z=m.product(x,x)
    assert z.lb==(0 if x.lb<=0<=x.ub else min(x.lb*x.lb,x.ub*x.ub))
    assert z.ub==max(x.lb*x.lb,x.ub*x.ub)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for v in range(x.lb,x.ub+1):
            inputs=atoms(m,x,v);out=atoms(m,z,v*v)
            assert solver.solve(assumptions=inputs+out)
            for bit in out:assert not solver.solve(assumptions=inputs+[-bit])


def test_product_reuse_named_views_constants_and_linear_operands():
    m=Model();x=m.int('x',-3,4);y=m.int('y',1,6)
    product=m.product(x,y)
    before=(m._top_id(),len(m._hard),len(m._pending_literal_defs))
    assert m.product(y,x) is product
    assert before==(m._top_id(),len(m._hard),len(m._pending_literal_defs))
    named=m.product(y,x,name='p')
    assert named.name=='p' and named is not product
    assert before==(m._top_id(),len(m._hard),len(m._pending_literal_defs))
    with pytest.raises(ValueError):m.product(x,y,name='p')
    assert m.product(1,x) is x and m.product(True,x) is x
    zero=m.product(False,x);assert zero.lb==zero.ub==0
    negative=m.product(-3,x)
    linear=m.product(x+1,y-2)
    assert m.product(y-2,x+1) is linear
    m &= x==3;m &= y==5
    result=m.solve()
    assert result.ok and [result[v] for v in [product,named,negative,linear]]==[15,15,-9,12]


@pytest.mark.parametrize('threshold',[None,2,64])
@pytest.mark.parametrize('expression',['variable','difference','weighted','lazy'])
def test_exact_abs_independent_of_objective(threshold,expression):
    m=Model();m.set_integer_binary_threshold(threshold)
    x=m.int('x',-5,5);y=m.int('y',-2,3)
    src={'variable':x,'difference':x-y,'weighted':2*x-3*y+1,'lazy':x//2}[expression]
    lazy=abs(src);out=m.abs(src)
    assert isinstance(lazy,AbsExpr)
    m &= lazy==out
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for a,b in itertools.product(range(-5,6),range(-2,4)):
            expected=abs({'variable':a,'difference':a-b,'weighted':2*a-3*b+1,'lazy':a//2}[expression])
            inputs=atoms(m,x,a)+atoms(m,y,b);output=atoms(m,out,expected)
            assert solver.solve(assumptions=inputs+output)
            for bit in output:assert not solver.solve(assumptions=inputs+[-bit])


def test_abs_is_lazy_reusable_and_decodable_from_saved_assignments():
    m=Model();x=m.int('x',-5,7);source=x+1
    before=(m._top_id(),len(m._hard),len(m._pending_literal_defs))
    lazy=abs(source)
    assert (lazy.lb,lazy.ub)==(0,8) and abs(lazy) is lazy
    assert before==(m._top_id(),len(m._hard),len(m._pending_literal_defs))
    source.constant=100 # The lazy expression keeps the original linear expression.
    m &= x==-3
    saved=m.solve();assert saved[lazy]==2
    out=m.abs(x+1);assert m.abs(-(x+1)) is out
    m &= lazy==2
    assert lazy._realized is out
    named=m.abs(x+1,name='magnitude');assert named.name=='magnitude'
    with pytest.raises(ValueError):m.abs(x,name='magnitude')
    result=m.solve();assert result.ok and result[out]==result[named]==2
    assert saved[lazy]==2


def test_abs_known_sign_constant_folding_and_objective():
    m=Model();positive=m.int('positive',2,7);negative=m.int('negative',-8,-3)
    assert m.abs(positive) is positive
    assert m.abs(negative) is m.scale(negative,-1)
    assert m.abs(-9).lb==m.abs(-9).ub==9
    assert abs(PBExpr.from_item(-3))==3
    x=m.int('x',-5,5)
    m &= x>=2
    m.obj += abs(x-1)
    result=m.solve()
    assert result.proven and result[x]==2 and result.cost==1


def test_reified_and_gated_uses_do_not_weaken_product_or_abs_definitions():
    m=Model();x=m.int('x',-2,3);y=m.int('y',-1,3);gate=m.bool('gate')
    product=m.product(x,y);magnitude=abs(x-y)
    m &= (product>=2).iff(gate)
    m &= (magnitude==2).only_if(gate)
    with Solver(name='g4',bootstrap_with=m.to_cnf().clauses) as solver:
        for a,b,enabled in itertools.product(range(-2,4),range(-1,4),[False,True]):
            expected=(enabled==(a*b>=2)) and (not enabled or abs(a-b)==2)
            inputs=atoms(m,x,a)+atoms(m,y,b)+[gate.id if enabled else -gate.id]
            assert solver.solve(assumptions=inputs)==expected


def test_nonlinear_operations_work_after_incremental_sat_solve():
    m=Model();x=m.int('x',-8,8);y=m.int('y',1,7)
    m &= x>=2
    assert m.solve().ok
    product=m.product(x,y);magnitude=abs(x-y)
    m &= product==12;m &= magnitude==1
    result=m.solve()
    assert result.ok and result[product]==12 and result[magnitude]==1


def test_foreign_models_invalid_types_and_operator_guidance():
    m=Model();x=m.int('x',-2,3);other=Model().int('other',0,4)
    foreign_term = 2 * other._model.bool('foreign')
    before=m._top_id(),len(m._hard)
    for call in [lambda:m.product(x,other),lambda:m.abs(other),
                 lambda:m.product(x,foreign_term),lambda:m.abs(foreign_term)]:
        with pytest.raises(ValueError,match='different model'):call()
    assert before==(m._top_id(),len(m._hard))
    for value in [None,1.5,'x',object()]:
        with pytest.raises(TypeError):m.product(x,value)
        with pytest.raises(TypeError):m.abs(value)
    with pytest.raises(TypeError):abs(.5*m.bool('b'))
    with pytest.raises(TypeError,match=r'model.product'):x*x
    with pytest.raises(TypeError,match=r'model.product'):m.bool('c')*x
