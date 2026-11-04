"""Binary-primary integers and on-demand scalar comparison predicates."""

from bisect import bisect_left
from collections.abc import Sequence
from math import gcd

from .expressions import Clause, ClauseGroup, PBExpr, Term


class NoOrderThresholds(Sequence):
    """Catch accidental entry into an order-only encoder."""

    def __len__(self):
        raise TypeError("Binary-backed IntVar has no order threshold sequence.")

    def __getitem__(self, index):
        raise TypeError("Binary-backed IntVar has no order threshold sequence.")


def initialize(integer):
    model = integer._model
    width = integer.ub - integer.lb
    integer._binary_primary = True
    integer._binary_view = tuple(model.fresh_internal_bool().id for _ in range(width.bit_length()))
    model._binary_int_bits.update(integer._binary_view)
    # Exclude padded bit patterns. Each zero in the upper bound contributes
    # one lexicographic cut; no domain values or threshold bits are enumerated.
    bits = integer._binary_view
    for i, bit in enumerate(bits):
        if not width & (1 << i):
            model._hard.append((-bit, *(-bits[j] for j in range(i + 1, len(bits)) if width & (1 << j))))


def as_pbexpr(integer):
    model = integer._model
    return PBExpr(model, [Term(1 << i, model._dimacs_to_lit(bit))
                          for i, bit in enumerate(integer._binary_view)], integer.lb)


def uses_binary_integer(model, lhs, rhs):
    return bool(model._binary_int_bits) and any(
        term.literal.id in model._binary_int_bits for expr in (lhs, rhs) for term in expr.terms
    )


def equal_relation(left, right, *, negate=False):
    """Compare binary offsets directly when their origins agree."""
    if not (left._binary_primary and right._binary_primary and left.lb == right.lb):
        return None
    model = left._model
    a, b = left._binary_view, right._binary_view
    clauses, differences = [], []
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else None
        y = b[i] if i < len(b) else None
        if x == y:
            continue
        if x is None or y is None:
            bit = y if x is None else x
            if negate:
                differences.append(bit)
            else:
                clauses.append([-bit])
        elif negate:
            difference = model.fresh_internal_bool()
            d = difference.id
            definition = [[-x, -y, -d], [x, y, -d],
                          [x, -y, d], [-x, y, d]]
            model._register_literal_definition(
                difference, ClauseGroup._from_dimacs_trusted(model, definition)
            )
            differences.append(d)
        else:
            clauses.extend([[-x, y], [x, -y]])
    if negate:
        clauses.append(differences)
    return ClauseGroup._from_dimacs_trusted(model, clauses)


def order_relation(left, right, shift=0):
    """Encode left <= right + shift directly for aligned binary offsets.

    Each state witnesses that the low bits satisfy the comparison. Only
    implications from the next state are needed: the final state is required
    true and intermediate states are existential, private to this relation.
    Strict comparison starts with a false state instead of a true one.
    """
    if not (left._binary_primary and right._binary_primary):
        return None
    delta = right.lb + shift - left.lb
    if delta not in (0, -1):
        return None
    model = left._model
    a, b = left._binary_view, right._binary_view
    pairs = [(a[i] if i < len(a) else False,
              b[i] if i < len(b) else False)
             for i in range(max(len(a), len(b)))]
    pairs = [(x, y) for x, y in pairs if x != y]
    if not pairs:
        return ClauseGroup._from_dimacs_trusted(model, [] if delta == 0 else [[]])
    clauses = []

    def neg(literal):
        return not literal if isinstance(literal, bool) else -literal

    def emit(*row):
        if any(literal is True for literal in row):
            return
        clauses.append(list(dict.fromkeys(literal for literal in row if literal is not False)))

    state = delta == 0
    for i, (x, y) in enumerate(pairs):
        out = True if i == len(pairs) - 1 else model.fresh_internal_bool().id
        # out -> majority(~x, y, state).
        emit(neg(out), neg(x), y)
        emit(neg(out), neg(x), state)
        emit(neg(out), y, state)
        state = out
    return ClauseGroup._from_dimacs_trusted(model, clauses)


def compile_pb(model, lhs, op, rhs):
    """Route binary-primary arithmetic to bounded BDD/adder selection."""
    from hermax.encoder._packed import PBEnc
    from hermax.encoder.pb_enc import EncType
    from .encoders import _EncoderDispatch
    from ._integer_affine import extract_integer_sum

    # Preserve complete order-backed operands in mixed expressions: channel
    # them once to reusable binary views instead of feeding every threshold
    # into the adder. Residual predicates remain ordinary Boolean terms.
    affine = extract_integer_sum(model, lhs - rhs)
    if affine is not None:
        lhs = PBExpr(model, [Term(coefficient * (1 << i), model._dimacs_to_lit(bit))
                             for owner, coefficient in affine.items
                             for i, bit in enumerate(owner._get_binary_view())], affine.constant)
        rhs = PBExpr.from_item(0)
    pairs, constant = _EncoderDispatch._normalize_pb(lhs, rhs)
    comparator, bound = _EncoderDispatch._bound_from_zero_compare(op, constant)
    divisor = gcd(*(weight for weight, _ in pairs)) if pairs else 1
    if divisor > 1:
        if comparator == "==" and bound % divisor:
            return ClauseGroup._from_dimacs_trusted(model, [[]])
        pairs = [(weight // divisor, literal) for weight, literal in pairs]
        bound = -((-bound) // divisor) if comparator == ">=" else bound // divisor
    total = sum(weight for weight, _ in pairs)
    impossible = bound < 0 if comparator in ("<=", "==") else bound > total
    impossible |= comparator == "==" and bound > total
    satisfied = (comparator == "<=" and bound >= total) or (comparator == ">=" and bound <= 0)
    if impossible or satisfied or not pairs:
        value = not impossible and (satisfied or bound == 0)
        return ClauseGroup._from_dimacs_trusted(model, [] if value else [[]])
    if model._inc_state.bound:
        model._reserve_literal_ids_up_to(int(model._inc_state.ip_next_vid))
    method = {"<=": PBEnc.leq, ">=": PBEnc.geq, "==": PBEnc.equals}[comparator]
    cnf = method(lits=[model._lit_to_dimacs(lit) for _, lit in pairs],
                 weights=[weight for weight, _ in pairs], bound=bound,
                 top_id=model._top_id(), encoding=EncType.bounded)
    model._debug(model.DEBUG_COMPILE, f"encode path=binary_int_bounded op={op} clauses={len(cnf.clauses)}")
    return model._cnfplus_to_clausegroup(cnf)


def comparison(integer, tag, value):
    owner = integer._encoding_owner()
    if owner is not integer:
        return comparison(owner, tag, value - integer.lb + owner.lb)
    if tag == "<":
        return ~comparison(integer, ">=", value)
    if tag == "<=":
        return ~comparison(integer, ">=", value + 1)
    if tag == ">":
        return comparison(integer, ">=", value + 1)
    if tag != ">=":
        raise ValueError(f"Unknown comparison tag {tag!r}")
    model = integer._model
    if value <= integer.lb:
        return model._get_bool_constant_literal(True)
    if value > integer.ub:
        return model._get_bool_constant_literal(False)
    key = (tag, value)
    if key in integer._cmp_cache:
        return integer._cmp_cache[key]
    predicate = model._predicate_bool(lambda result: result[integer] >= value)
    if integer._binary_comparisons is None:
        integer._binary_comparisons = ({}, [])
    gates, thresholds = integer._binary_comparisons
    bound = value - integer.lb
    state = True
    clauses = []
    # Read the constant from low to high bits. A 1 requires AND with the
    # previous comparison; a 0 requires OR. This uses O(bit width) gates.
    for i, bit_id in enumerate(integer._binary_view):
        bit = model._dimacs_to_lit(bit_id)
        is_and = bool(bound & (1 << i))
        if state is True:
            state = bit if is_and else True
            continue
        # The comparison of the low i+1 bits depends only on this constant
        # suffix. Reuse it across thresholds of the same encoding owner.
        gate_key = (i, bound & ((1 << (i + 1)) - 1))
        if gate_key in gates:
            state = gates[gate_key]
            continue
        out = model.fresh_internal_bool()
        if is_and:
            definition = (Clause(model, [~out, bit]), Clause(model, [~out, state]),
                          Clause(model, [out, ~bit, ~state]))
        else:
            definition = (Clause(model, [~bit, out]), Clause(model, [~state, out]),
                          Clause(model, [~out, bit, state]))
        model._register_literal_definition(out, ClauseGroup(model, definition))
        gates[gate_key] = out
        state = out
    clauses.extend(model._equiv_literals_group(predicate, state))
    # Link only the nearest requested thresholds. Previously emitted links
    # remain valid when a new threshold is inserted between their endpoints.
    # Post links separately so deferred definitions do not recursively depend
    # on an arbitrarily long threshold chain. Export realizes both endpoints.
    position = bisect_left(thresholds, value)
    if position:
        lower = integer._cmp_cache[">=", thresholds[position - 1]]
        model._hard.append((-predicate.id, lower.id))
    if position < len(thresholds):
        upper = integer._cmp_cache[">=", thresholds[position]]
        model._hard.append((-upper.id, predicate.id))
    model._register_literal_definition(predicate, ClauseGroup(model, clauses))
    integer._cmp_cache[key] = predicate
    thresholds.insert(position, value)
    return predicate


def equality(integer, value):
    if value not in integer._eq_lits:
        model = integer._model
        owner = integer._encoding_owner()
        if owner is not integer:
            literal = owner == value - integer.lb + owner.lb
        else:
            literal = model._predicate_bool(lambda result: result[integer] == value)
            atoms = integer._exact_value_atoms(value)
            clauses = [Clause(model, [~literal, atom]) for atom in atoms]
            clauses.append(Clause(model, [literal, *[~atom for atom in atoms]]))
            model._register_literal_definition(literal, ClauseGroup(model, clauses))
        integer._eq_lits[value] = literal
    return integer._eq_lits[value]
