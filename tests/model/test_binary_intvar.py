import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model, Literal


def fixed(variable, value):
    literals = variable._value_literals()
    if variable.encoding == "binary":
        return [lit.id if (value-variable.lb) & (1 << i) else -lit.id for i, lit in enumerate(literals)]
    return [lit.id if i < value-variable.lb else -lit.id for i, lit in enumerate(literals)]


def binary_model():
    model = Model()
    model.set_integer_binary_threshold(4)
    return model


def test_automatic_encoding_selection_and_setting():
    m = Model()
    assert m.int("below", 0, 62).encoding == "order"
    assert m.int("boundary", -32, 31).encoding == "binary"
    m.set_integer_binary_threshold(4)
    assert m.int("tiny", 0, 2).encoding == "order"
    assert m.int("four", -1, 2).encoding == "binary"
    m.set_integer_binary_threshold(None)
    assert m.int("ordered", 0, 100).encoding == "order"
    for invalid in [True, 1, 0, -1, 2.5, "64"]:
        with pytest.raises(ValueError):
            m.set_integer_binary_threshold(invalid)
    with pytest.raises(TypeError):
        Model(integer_encoding="binary")
    with pytest.raises(TypeError):
        Model(binary_min_domain=4)
    with pytest.raises(TypeError):
        m.int("removed", 0, 5, encoding="binary")


@pytest.mark.parametrize("bounds", [(0, 3), (-3, 1), (7, 15), (0, 31)])
def test_scalar_comparisons_and_padding(bounds):
    m = binary_model()
    x = m.int("x", *bounds)
    predicates = []
    for value in range(x.lb-1, x.ub+2):
        for compare in (operator.le, operator.lt, operator.ge, operator.gt):
            predicate = compare(x, value)
            assert isinstance(predicate, Literal)
            assert predicate is compare(x, value)
            predicates.append((predicate, compare, value))
    cnf = m.to_cnf()  # Materialize all predicates before using external SAT.
    with Solver(name="g4", bootstrap_with=cnf.clauses) as solver:
        for count in range(1 << len(x._binary_view)):
            bits = [bit if count & (1 << i) else -bit for i, bit in enumerate(x._binary_view)]
            valid = count <= x.ub-x.lb
            assert solver.solve(assumptions=bits) == valid
            if valid:
                for predicate, compare, value in predicates:
                    dim = m._lit_to_dimacs(predicate)
                    expected = compare(count+x.lb, value)
                    assert solver.solve(assumptions=bits+[dim if expected else -dim])
                    assert not solver.solve(assumptions=bits+[-dim if expected else dim])


@pytest.mark.parametrize("op", [operator.le, operator.lt, operator.ge, operator.gt, operator.eq, operator.ne])
@pytest.mark.parametrize("mixed", [False, True])
def test_binary_and_mixed_relations(op, mixed):
    m = binary_model()
    x = m.int("x", -2, 2)
    y = m.int("y", -1, 1 if mixed else 3)
    flag = m.bool()
    m &= op(x, y).iff(flag)
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, f in itertools.product(range(x.lb,x.ub+1), range(y.lb,y.ub+1), (False,True)):
            assert solver.solve(assumptions=fixed(x,a)+fixed(y,b)+[flag.id if f else -flag.id]) == (f == op(a,b))


@pytest.mark.parametrize("op", [operator.le, operator.lt, operator.ge, operator.gt, operator.eq, operator.ne])
def test_binary_weighted_arithmetic(op):
    m = binary_model()
    x, y, z = m.int("x",-2,2), m.int("y",0,2), m.int("z",-1,3)
    m &= op(2*x-3*y+z, 2)
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for a,b,c in itertools.product(range(-2,3),range(3),range(-1,4)):
            assert solver.solve(assumptions=fixed(x,a)+fixed(y,b)+fixed(z,c)) == op(2*a-3*b+c,2)


@pytest.mark.parametrize("op", [operator.le, operator.lt, operator.ge, operator.gt, operator.eq, operator.ne])
def test_binary_arithmetic_reduces_large_common_coefficients(op):
    m = binary_model()
    x, y, z = m.int("x",-2,2), m.int("y",0,2), m.int("z",-1,3)
    scale = 2**80
    m &= op(scale*(2*x-3*y+z),scale*2+1)
    with Solver(name="g4",bootstrap_with=m.to_cnf().clauses) as solver:
        for a,b,c in itertools.product(range(-2,3),range(3),range(-1,4)):
            assert solver.solve(assumptions=fixed(x,a)+fixed(y,b)+fixed(z,c)) == op(scale*(2*a-3*b+c),scale*2+1)


@pytest.mark.parametrize("divisor", [1, 2, 3, 7, 30])
def test_binary_derived_arithmetic(divisor):
    m = binary_model()
    x = m.int("x", -9, 10)
    q, r = m.floor_div(x,divisor), m.modulo(x,divisor)
    scaled = m.scale(x,-3)
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for value in range(x.lb,x.ub+1):
            assert solver.solve(assumptions=fixed(x,value))
            result = m.decode_model(solver.get_model())
            assert (result[q],result[r],result[scaled]) == (value//divisor,value%divisor,-3*value)


def test_binary_derived_definitions_work_from_high_bits():
    m = binary_model()
    x = m.int("x", 0, 63)
    q = m.floor_div(x, 2)
    m &= q >= 16
    m &= x <= 31
    assert not m.solve().ok


def test_order_input_can_produce_wide_binary_derived_values():
    m = binary_model()
    x = m.int("tiny",-1,1)
    assert x.encoding == "order"
    scaled, remainder = m.scale(x,10**17), m.modulo(x,10**17)
    assert scaled.encoding == remainder.encoding == "binary"
    with Solver(name="g4",bootstrap_with=m.to_cnf().clauses) as solver:
        for value in (-1,0,1):
            assert solver.solve(assumptions=fixed(x,value))
            result = m.decode_model(solver.get_model())
            assert result[scaled] == value*10**17
            assert result[remainder] == value%(10**17)
    assert m._top_id() < 3000


def test_binary_offset_views_reuse_bits_and_predicates():
    m = binary_model()
    x = m.int("x",-5,10)
    alias = m.scale(x,1,name="alias")
    shifted = m.modulo(m.int("n",10,13),7)
    assert alias._binary_view is x._binary_view
    assert (alias == 3) is (x == 3)
    assert (alias >= 3) is (x >= 3)
    m &= shifted == 5
    result = m.solve()
    assert result.ok and result[shifted] == 5


@pytest.mark.parametrize("kind", ["floor_div", "modulo", "scale", "max", "min", "sum_var"])
def test_binary_derived_values_under_guards(kind):
    m = binary_model()
    x, y = m.int("x",-2,3), m.int("y",0,3)
    if kind in ("floor_div", "modulo", "scale"):
        out = getattr(m,kind)(x,-2 if kind == "scale" else 3)
    else:
        out = getattr(m,kind)([x,y])
    gate, flag = m.bool(), m.bool()
    m &= (out >= 1).only_if(gate)
    m &= (out <= 2).iff(flag)
    functions = {"floor_div": lambda a,b: a//3, "modulo": lambda a,b: a%3,
                 "scale": lambda a,b: -2*a, "max": max, "min": min,
                 "sum_var": lambda a,b: a+b}
    with Solver(name="g4",bootstrap_with=m.to_cnf().clauses) as solver:
        for a,b,gv,fv in itertools.product(range(-2,4),range(4),(False,True),(False,True)):
            value = functions[kind](a,b)
            assumptions = fixed(x,a)+fixed(y,b)+[gate.id if gv else -gate.id,flag.id if fv else -flag.id]
            assert solver.solve(assumptions=assumptions) == ((not gv or value>=1) and fv==(value<=2))


@pytest.mark.parametrize("coefficient", [-3, 1, 4])
def test_binary_objective_signed_values(coefficient):
    m = binary_model()
    x = m.int("x",-5,7)
    m.obj += coefficient*x
    result = m.solve(time_limit=3)
    expected = 7 if coefficient < 0 else -5
    assert result.proven and result[x] == expected
    assert result.cost == coefficient*expected


def test_binary_creation_after_incremental_backend_reserves_ids():
    from tests.model.test_model_incremental_native import FakeIPSolver

    m = binary_model()
    m.obj += m.bool("cost")
    assert m.solve(incremental=True,backend="maxsat",solver=FakeIPSolver()).ok
    m._inc_state.ip_next_vid = 500
    x = m.int("x",0,10**17)
    m &= x >= 123456789
    assert min(x._binary_view) > 500
    m.close_incremental()


def test_binary_private_order_sequence_is_unavailable():
    x = Model().int("x",0,10**17)
    with pytest.raises(TypeError, match="no order threshold"):
        x._threshold_ids()


def test_mixed_arithmetic_reuses_order_to_binary_channels():
    m = Model()
    m.set_integer_binary_threshold(None)
    ordered = m.int("ordered",0,63)
    m.set_integer_binary_threshold(64)
    wide = m.int("wide",0,10**17)
    m &= 2*wide+3*ordered == 100
    view = ordered._binary_view
    assert view is not None
    m &= wide+ordered <= 70
    assert ordered._binary_view is view
    m &= wide >= 20
    m &= ordered >= 10
    result = m.solve(time_limit=3)
    assert result.ok and 2*result[wide]+3*result[ordered] == 100


def test_mixed_arithmetic_keeps_residual_order_predicates():
    m = Model()
    m.set_integer_binary_threshold(4)
    x = m.int("x",0,3)
    m.set_integer_binary_threshold(None)
    y = m.int("y",0,5)
    m &= 2*x+3*y+5*(y>=2) <= 12
    with Solver(name="g4",bootstrap_with=m.to_cnf().clauses) as solver:
        for a,b in itertools.product(range(4),range(6)):
            assert solver.solve(assumptions=fixed(x,a)+fixed(y,b)) == (2*a+3*b+5*(b>=2)<=12)


@pytest.mark.parametrize("lower,upper", [(0,5), (-8,-3), (-3,6)])
def test_binary_raw_decode_stays_in_domain_for_padded_patterns(lower, upper):
    m = binary_model()
    x = m.int("x",lower,upper)
    # decode_model accepts partial/raw assignments without requiring that
    # they satisfy the formula. Match the order decoder's clamping behavior.
    assert m.decode_model(list(x._binary_view))[x] == upper
    equality = x == lower+2
    raw = [*x._binary_view, equality.id]
    assert m.decode_model(raw)[x] == lower+2


@pytest.mark.parametrize("compare,label", [(operator.ge,"x>=5"), (operator.eq,"x==5")])
def test_binary_comparison_helpers_do_not_claim_user_names(compare, label):
    m = binary_model()
    named = m.bool(label)
    x = m.int("x",0,7)
    predicate = compare(x,5)
    assert predicate is compare(x,5)
    m &= ~named
    m &= predicate
    result = m.solve()
    assert result.ok and result[named] is False and compare(result[x],5)


def test_wide_arithmetic_aggregates_and_all_different_stay_small():
    m = binary_model()
    xs = m.int_vector("x",4,0,10**17)
    m &= xs.all_different()
    for x,value in zip(xs,[5,6,7,8]):
        m &= x == value
    lo, hi, total = m.min(xs), m.max(xs), m.sum_var(xs)
    q, r, scaled = m.floor_div(xs[0],7), m.modulo(xs[0],7), m.scale(xs[0],-2)
    result = m.solve(time_limit=5)
    assert result.ok
    assert [result[value] for value in (lo,hi,total,q,r,scaled)] == [5,8,26,0,5,-10]
    assert m._top_id() < 20000


def test_wide_objective_and_incremental_predicates():
    m = binary_model()
    x = m.int("x",0,10**17)
    m &= x <= 5
    m.obj += x
    first = m.solve(time_limit=3)
    assert first.proven and first[x] == 0
    late = x >= 2
    assert first[late] is False
    m &= late
    second = m.solve(time_limit=3)
    assert second.proven and second[x] == 2
    assert first[x] == 0 and first[late] is False
    assert m._top_id() < 2000


def test_binary_set_cardinality_and_materialized_bounds():
    m = binary_model()
    selected = m.int_set("selected", lb=0, ub=5)
    count = selected.card()
    m &= count == 4
    xs = m.int_vector("x",3,0,10)
    upper, lower = xs.upper_bound()._realize(), xs.lower_bound()._realize()
    for x in xs:
        m &= x == 5
    result = m.solve()
    assert result.ok and len(result[selected]) == 4
    assert result[upper] >= 5 and result[lower] <= 5


@pytest.mark.parametrize("backend", ["auto", "time", "task"])
@pytest.mark.parametrize("mode", ["post", "iff", "gated_iff"])
def test_binary_cumulative_uses_variable_start_events(backend, mode):
    m = binary_model()
    starts = m.int_vector("s",3,0,3)
    flag, gate = m.bool(), m.bool()
    durations, demands, capacity = [2,1,2], [1,2,1], 2
    condition = m.cumulative(starts,durations,demands,capacity,backend=backend)
    if mode == "gated_iff":
        condition = condition.only_if(gate).iff(flag)
    elif mode == "iff":
        condition = condition.iff(flag)
    m &= condition
    with Solver(name="g4",bootstrap_with=m.to_cnf().clauses) as solver:
        for values,fv,gv in itertools.product(itertools.product(range(4),repeat=3),(False,True),(False,True)):
            truth = all(sum(r for s,d,r in zip(values,durations,demands) if s<=t<s+d)<=capacity for t in range(6))
            expected = truth if mode == "post" else fv==truth if mode == "iff" else fv==(not gv or truth)
            assumptions = [lit for s,value in zip(starts,values) for lit in fixed(s,value)]
            assumptions += [flag.id if fv else -flag.id,gate.id if gv else -gate.id]
            assert solver.solve(assumptions=assumptions) == expected


def test_wide_cumulative_does_not_enumerate_times():
    m = binary_model()
    starts = m.int_vector("s",3,0,10**17)
    flag = m.bool()
    m &= m.cumulative(starts,[2]*3,[1]*3,2).iff(flag)
    for start in starts:
        m &= start == 5
    result = m.solve(time_limit=3)
    assert result.ok and result[flag] is False
    assert m._top_id() < 10000


def test_direct_ten_digit_divisibility_formulation():
    m = binary_model()
    digits = m.int_vector("digits",10,0,9)
    m &= digits.all_different()
    known = [3,8,1,6,5,4,7,2,9,0]
    for n in range(1,11):
        weights = [10**(n-1-j) for j in range(n)]
        quotient = m.int(f"q{n}",0,sum(9*w for w in weights)//n)
        m &= sum(w*digits[j] for j,w in enumerate(weights)) == n*quotient
    # Validate the direct large-coefficient formulation without depending on
    # the search time required to discover this particular solution.
    for digit,value in zip(digits,known):
        m &= digit == value
    result = m.solve(time_limit=5)
    assert result.ok and result[digits] == known
    assert m._top_id() < 10000


@pytest.mark.parametrize('order', [(2, 4, 6), (6, 4, 2), (2, 6, 4)])
def test_binary_threshold_neighbours_propagate_in_both_directions(order):
    m = binary_model()
    x = m.int('x', -3, 7)
    predicates = {t: x >= t for t in order}
    with Solver(name='g4', bootstrap_with=m.to_cnf().clauses) as solver:
        for lower, upper in itertools.combinations(sorted(order), 2):
            ok, forced = solver.propagate(assumptions=[predicates[upper].id])
            assert ok and predicates[lower].id in forced
            ok, forced = solver.propagate(assumptions=[-predicates[lower].id])
            assert ok and -predicates[upper].id in forced


def test_binary_thresholds_share_gates_and_offset_owner():
    m = binary_model()
    x = m.int('x', 0, 31)
    predicates = [x >= t for t in range(1, 32)]
    gates, thresholds = x._binary_comparisons
    assert thresholds == list(range(1, 32))
    assert len(gates) == 52
    alias = type(x)._from_offset(x, 7, 'shifted')
    assert (alias >= 20) is predicates[12]
    cnf = m.to_cnf()
    assert cnf.nv == 88
    assert len(cnf.clauses) == 248


def test_binary_threshold_insertion_after_export_keeps_literals_and_definitions():
    m = binary_model()
    x = m.int('x', 0, 15)
    low, high = x >= 3, x >= 12
    first = m.to_cnf()
    middle = x >= 7
    assert (x >= 3) is low and (x >= 12) is high
    second = m.to_cnf()
    # Exercise append-only use with an already existing SAT solver.
    with Solver(name='g4', bootstrap_with=first.clauses) as solver:
        solver.append_formula(list(second.clauses)[len(first.clauses):])
        for value in range(16):
            bits = fixed(x, value)
            for threshold, predicate in [(3, low), (7, middle), (12, high)]:
                assert not solver.solve(assumptions=bits + [-predicate.id if value >= threshold else predicate.id])
        ok, forced = solver.propagate(assumptions=[high.id])
        assert ok and middle.id in forced and low.id in forced


def test_many_pending_binary_thresholds_do_not_recurse_through_neighbours():
    m = binary_model()
    x = m.int('x', 0, 2000)
    predicates = [x >= t for t in range(1, 1001)]
    m &= predicates[-1]
    cnf = m.to_cnf()
    with Solver(name='g4', bootstrap_with=cnf.clauses) as solver:
        assert solver.solve(assumptions=fixed(x, 1000))
        assert not solver.solve(assumptions=fixed(x, 999))


@pytest.mark.parametrize('op', [operator.eq, operator.ne, operator.lt, operator.le, operator.gt, operator.ge])
@pytest.mark.parametrize('bounds', [((-3, 1), (-3, 8)), ((0, 7), (0, 7)), ((-4, 3), (0, 7))])
def test_direct_binary_relations_reify_different_widths_and_origins(op, bounds):
    m = binary_model()
    x, y = m.int('x', *bounds[0]), m.int('y', *bounds[1])
    flag = m.bool()
    m &= op(x, y).iff(flag)
    with Solver(name='g4', bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, f in itertools.product(range(x.lb, x.ub+1), range(y.lb, y.ub+1), (False, True)):
            assert solver.solve(assumptions=fixed(x, a)+fixed(y, b)+[flag.id if f else -flag.id]) == (f == op(a, b))


def test_direct_binary_equality_has_no_auxiliaries():
    m = Model()
    x, y = m.int('x', 0, 2**20-1), m.int('y', 0, 2**20-1)
    m &= x == y
    cnf = m.to_cnf()
    assert cnf.nv == 40
    assert len(cnf.clauses) == 40


@pytest.mark.parametrize('op', [operator.lt, operator.le, operator.gt, operator.ge])
@pytest.mark.parametrize('alias', [False, True])
def test_direct_binary_order_guards_and_offset_views(op, alias):
    m = binary_model()
    source = m.int('source', -3, 4)
    x = type(source)._from_offset(source, 5, 'shifted')
    y = type(source)._from_offset(source, 5, 'alias') if alias else m.int('y', 2, 13)
    flag = m.bool()
    m &= op(x, y).only_if(flag)
    with Solver(name='g4', bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, f in itertools.product(range(x.lb, x.ub+1), range(y.lb, y.ub+1), (False, True)):
            expected = (not alias or a == b) and (not f or op(a, b))
            assert solver.solve(assumptions=fixed(x, a)+fixed(y, b)+[flag.id if f else -flag.id]) == expected


@pytest.mark.parametrize('op', [operator.lt, operator.le, operator.gt, operator.ge])
def test_direct_binary_order_size(op):
    m = Model()
    x, y = m.int('x', 0, 2**20-1), m.int('y', 0, 2**20-1)
    m &= op(x, y)
    cnf = m.to_cnf()
    assert cnf.nv == 59
    assert len(cnf.clauses) <= 60
