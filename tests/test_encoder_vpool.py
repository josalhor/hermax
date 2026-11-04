import pytest
from pysat.formula import IDPool
from pysat.solvers import Solver

from hermax.encoder.pb_enc import EncType, PBEnc


def test_pb_encoder_handles_occupied_id_pool_ranges_with_auxiliaries():
    pool = IDPool()
    pool.top = 4
    pool.occupy(9, 11)

    cnf = PBEnc.leq(
        lits=[1, 2, 3, 4],
        weights=[1, 1, 1, 1],
        bound=2,
        vpool=pool,
        encoding=EncType.bdd,
    )

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert solver.solve(assumptions=[1, 2, -3, -4])
        assert not solver.solve(assumptions=[1, 2, 3, -4])


@pytest.mark.parametrize('backend', ['public', 'packed'])
@pytest.mark.parametrize('encoding', [1, 6, 7, 8])
@pytest.mark.parametrize('operation,bound', [('atmost', 1), ('atleast', 2), ('equals', 1)])
@pytest.mark.parametrize('occupied', [[[4, 10]], [[1, 3], [5, 20]], [[2, 8], [8, 12]], []])
def test_cardinality_pool_remapping_preserves_input_and_occupied_ids(backend, encoding, operation, bound, occupied):
    import itertools
    from hermax.encoder.card import CardEnc
    from hermax.encoder._packed import CardEnc as PackedCardEnc

    encoder = CardEnc if backend == 'public' else PackedCardEnc
    # Negative literals are deliberate; input IDs were not created by pool.
    lits = [1, -2, 3]
    pool = IDPool(occupied=[list(interval) for interval in occupied])
    cnf = getattr(encoder, operation)(lits, bound=bound, vpool=pool, encoding=encoding)
    aux = {abs(lit) for clause in cnf.clauses for lit in clause} - {1, 2, 3}
    assert all(not start <= lit <= end for lit in aux for start, end in occupied)
    assert pool.top >= max([3, *aux])
    with Solver(name='g3', bootstrap_with=cnf.clauses) as solver:
        for bits in itertools.product([False, True], repeat=3):
            count = sum(bits[abs(lit)-1] == (lit > 0) for lit in lits)
            expected = {'atmost': count <= bound, 'atleast': count >= bound, 'equals': count == bound}[operation]
            assert solver.solve(assumptions=[i if value else -i for i, value in enumerate(bits, 1)]) == expected


@pytest.mark.parametrize('backend', ['public', 'packed'])
@pytest.mark.parametrize('encoding', [0, 1, 2, 3, 4, 5, 7])
@pytest.mark.parametrize('operation', ['leq', 'geq', 'equals'])
def test_pb_pool_remapping_preserves_conditionals_and_arithmetic(backend, encoding, operation):
    import itertools
    from hermax.encoder._packed import PBEnc as PackedPBEnc

    encoder = PBEnc if backend == 'public' else PackedPBEnc
    lits = [1, -2, 3, 4]
    weights = [2, 3, 4, 5]
    conditionals = [11, -12]
    pool = IDPool(occupied=[[5, 20]])
    cnf = getattr(encoder, operation)(lits=lits, weights=weights, bound=5, vpool=pool,
                                      encoding=encoding, conditionals=conditionals)
    original = {1, 2, 3, 4, 11, 12}
    aux = {abs(lit) for clause in cnf.clauses for lit in clause} - original
    assert all(lit > 20 for lit in aux)
    assert pool.top >= max([12, *aux])
    with Solver(name='g3', bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product([False, True], repeat=6):
            assignment = dict(zip([1, 2, 3, 4, 11, 12], values))
            active = lambda lit: assignment[abs(lit)] == (lit > 0)
            total = sum(weight for lit, weight in zip(lits, weights) if active(lit))
            comparison = {'leq': total <= 5, 'geq': total >= 5, 'equals': total == 5}[operation]
            expected = not all(active(lit) for lit in conditionals) or comparison
            assumptions = [var if value else -var for var, value in assignment.items()]
            assert solver.solve(assumptions=assumptions) == expected


@pytest.mark.parametrize('backend', ['public', 'packed'])
def test_pool_reserves_inputs_when_no_auxiliary_is_generated(backend):
    from hermax.encoder.card import CardEnc
    from hermax.encoder._packed import CardEnc as PackedCardEnc, PBEnc as PackedPBEnc

    card = CardEnc if backend == 'public' else PackedCardEnc
    pb = PBEnc if backend == 'public' else PackedPBEnc
    for operation, bound in [('atmost', 3), ('atleast', 1)]:
        pool = IDPool(occupied=[[1, 10]])
        cnf = getattr(card, operation)([1, 2, 3], bound=bound, vpool=pool)
        assert cnf.nv >= 3
        assert pool.top >= 10
        assert pool.id() > 10
    for encoding in [0, 6]:
        pool = IDPool(occupied=[[1, 10]])
        cnf = pb.leq([1, 2, 3], weights=[1, 1, 1], bound=3, vpool=pool, encoding=encoding)
        assert cnf.nv >= 3
        assert pool.top >= 10
        assert pool.id() > 10


@pytest.mark.parametrize('backend', ['public', 'packed'])
def test_empty_pb_reserves_conditional_and_pool_ids(backend):
    from hermax.encoder._packed import PBEnc as PackedPBEnc
    encoder = PBEnc if backend == 'public' else PackedPBEnc
    pool = IDPool(occupied=[[4, 12]])
    cnf = encoder.equals([], weights=[], bound=1, conditionals=[-8], vpool=pool)
    assert list(cnf.clauses) == [(8,)]
    assert cnf.nv >= 8 and pool.top >= 12


def test_cardinality_trivial_results_preserve_top_id():
    from hermax.encoder.card import CardEnc, EncType as CardType
    for operation, bound in [('atmost', 3), ('atleast', 0), ('equals', 0)]:
        cnf = getattr(CardEnc, operation)([1, 2, 3], bound=bound, top_id=100,
                                          encoding=CardType.kmtotalizer)
        assert cnf.nv >= 100
