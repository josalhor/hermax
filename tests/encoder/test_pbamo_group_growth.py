"""Large supplied AMO groups must stay compact and remain enforced."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.encoder import pbamo
from hermax.encoder._packed import PBAMOEnc as PackedPBAMOEnc
from hermax.model import Model


@pytest.mark.parametrize("policy", [pbamo.OverlapPolicy.baseline_paper, pbamo.OverlapPolicy.paper_best_fit_dynamic_future])
def test_disjoint_candidates_do_not_expand_pair_support(monkeypatch, policy):
    def reject(*args):
        raise AssertionError("disjoint AMO groups were expanded into pairs")

    monkeypatch.setattr(pbamo, "_pair_support_maps", reject)
    lits = list(range(1, 1025))
    partition = pbamo.choose_overlap_partition(
        lits, [1] * len(lits), amo_groups=[lits[:512]], eo_groups=[lits[512:]], policy=policy,
    )
    assert {frozenset(group) for group in partition} == {frozenset(lits[:512]), frozenset(lits[512:])}


@pytest.mark.parametrize("policy", [pbamo.OverlapPolicy.baseline_paper, pbamo.OverlapPolicy.paper_best_fit_dynamic_future])
def test_disjoint_partition_preserves_existing_order(policy):
    rng = random.Random(582)
    for _ in range(50):
        lits = [i * rng.choice([-1, 1]) for i in range(1, 17)]
        rng.shuffle(lits)
        weights = [rng.randrange(1, 10) for _ in lits]
        groups = [lits[:5], lits[5:8], lits[8:12]]
        amo, eo = groups[:2] + [groups[0]], groups[2:] + [[lits[0]]]
        pair, eo_pair, neighbors = pbamo._pair_support_maps(lits, amo, eo)
        expected = (pbamo._baseline_overlap_partition(lits, neighbors)
                    if policy == pbamo.OverlapPolicy.baseline_paper else
                    pbamo._DynamicOverlapPartition(lits, dict(zip(lits, weights)), pair, eo_pair, neighbors).partition())
        assert pbamo.choose_overlap_partition(lits, weights, amo_groups=amo, eo_groups=eo, policy=policy) == expected


@pytest.mark.parametrize("encoder", [pbamo.PBAMOEnc, PackedPBAMOEnc])
@pytest.mark.parametrize("method", ["auto_leq", "auto_eq"])
@pytest.mark.parametrize("bound", [1, 3, 6, 144])
def test_compact_overlapping_candidates_are_enforced(encoder, method, bound):
    lits = [i if i % 2 else -i for i in range(1, 49)]
    weights = [i % 5 + 1 for i in range(48)]
    amo, eo = [lits[:32], lits[16:]], [lits[:32]]
    cnf = getattr(encoder, method)(lits=lits, weights=weights, bound=bound,
                                   amo_groups=amo, eo_groups=eo, top_id=1000)
    assert all(0 < abs(lit) <= cnf.nv and (abs(lit) <= 48 or abs(lit) > 1000)
               for clause in cnf.clauses for lit in clause)
    free = [0, 1, 2, 45, 46, 47]
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for bits in itertools.product([False, True], repeat=len(free)):
            active = dict.fromkeys(lits, False)
            active.update((lits[i], bit) for i, bit in zip(free, bits))
            total = sum(w for lit, w in zip(lits, weights) if active[lit])
            expected = total <= bound if method == "auto_leq" else total == bound
            expected &= all(sum(active[lit] for lit in group) <= 1 for group in amo)
            expected &= all(sum(active[lit] for lit in group) == 1 for group in eo)
            assert solver.solve(assumptions=[lit if active[lit] else -lit for lit in lits]) == expected


@pytest.mark.parametrize("kind", ["at_most_one", "exactly_one"])
def test_model_large_amo_eo_uses_linear_candidate_encoding(kind):
    m = Model()
    bits = m.bool_vector("b", 1024)
    m &= getattr(bits, kind)()
    cnf = m.to_cnf()
    assert len(cnf.clauses) < 5000
    groups = m._known_eo_groups if kind == "exactly_one" else m._known_amo_groups
    assert list(groups.values()) == [tuple(m._lit_to_dimacs(lit) for lit in bits)]
    with Solver(bootstrap_with=cnf.clauses) as solver:
        assert not solver.solve(assumptions=[bits[0].id, bits[-1].id])
        assert solver.solve(assumptions=[bits[0].id])
        assert solver.solve(assumptions=[-lit.id for lit in bits]) == (kind == "at_most_one")


@pytest.mark.parametrize("encoder", ["mdd", "gswc", "ggpw", "gmto", "rggt"])
def test_native_group_emission_is_compact_and_exact(encoder):
    from hermax.internal import _pbamo

    lits = [i if i % 2 else -i for i in range(1, 65)]
    weights = [i % 4 + 1 for i in range(64)]
    clauses, nv = _pbamo.encode_leq(
        wlits=list(zip(lits, weights)), groups=[lits], bound=10,
        top_id=5000, encoder=encoder, emit_amo=True,
    )
    assert len(clauses) < 500
    assert all(abs(lit) <= 64 or 5000 < abs(lit) <= nv for clause in clauses for lit in clause)
    with Solver(bootstrap_with=clauses) as solver:
        for bits in itertools.product([False, True], repeat=6):
            active = list(bits) + [False] * 58
            assert solver.solve(assumptions=[lit if bit else -lit for lit, bit in zip(lits, active)]) == (sum(bits) <= 1)


def test_native_equality_group_emission_is_compact_and_exact():
    from hermax.internal import _pbamo

    lits = list(range(1, 65))
    weights = [i % 4 + 1 for i in range(64)]
    clauses, nv = _pbamo.encode_eq(
        wlits=list(zip(lits, weights)), groups=[lits], bound=3,
        top_id=5000, encoder="rggt", emit_amo=True,
    )
    assert len(clauses) < 500
    assert nv >= 5000
    with Solver(bootstrap_with=clauses) as solver:
        for bits in itertools.product([False, True], repeat=6):
            assumptions = [i + 1 if bit else -(i + 1) for i, bit in enumerate(bits)]
            assumptions += [-i for i in range(7, 65)]
            expected = sum(bits) == 1 and sum(w for w, bit in zip(weights, bits) if bit) == 3
            assert solver.solve(assumptions=assumptions) == expected


@pytest.mark.parametrize("backend", [pbamo.PBAMOEnc, PackedPBAMOEnc])
@pytest.mark.parametrize("method,bound,expected", [
    ("auto_leq", 1, None), ("auto_leq", 2, "kmtotalizer"),
    ("auto_eq", 1, None), ("auto_eq", 2, "kmtotalizer"),
    ("auto_eq", 5, None),
])
def test_flat_amo_uses_shared_policy_without_changing_general_counts(backend, method, bound, expected):
    from hermax.encoder.card import EncType

    original = backend._card_encoder
    selected = []

    class RecordingCard(original):
        @classmethod
        def atmost(cls, **kwargs):
            selected.append(kwargs["encoding"])
            return original.atmost(**kwargs)

        @classmethod
        def equals(cls, **kwargs):
            selected.append(kwargs["encoding"])
            return original.equals(**kwargs)

    class RecordingBackend(backend):
        _card_encoder = RecordingCard

    lits = [1, -2, 3, -4, 5, -6]
    cnf = getattr(RecordingBackend, method)(lits=lits, weights=[1] * 6, bound=bound, top_id=20)
    assert selected == ([] if expected is None else [getattr(EncType, expected)])
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for bits in itertools.product([False, True], repeat=6):
            count = sum(bits)
            truth = count <= bound if method == "auto_leq" else count == bound
            assert solver.solve(assumptions=[lit if bit else -lit for lit, bit in zip(lits, bits)]) == truth


@pytest.mark.parametrize("backend", [pbamo.PBAMOEnc, PackedPBAMOEnc])
@pytest.mark.parametrize("method", ["auto_leq", "auto_eq", "_auto_atmost"])
def test_amo_routing_precedes_overlap_partitioning(monkeypatch, backend, method):
    def reject(*args, **kwargs):
        raise AssertionError("AMO/EO entered overlap partitioning")

    monkeypatch.setattr(pbamo, "choose_overlap_partition", reject)
    lits = [1, -2, 3, -4, 5, -6]
    kwargs = dict(lits=lits, bound=1, amo_groups=[lits[:4], lits[2:]], eo_groups=[lits[:3], lits[1:4]], top_id=20)
    if method != "_auto_atmost":
        kwargs["weights"] = [1] * len(lits)
    cnf = getattr(backend, method)(**kwargs)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for bits in itertools.product([False, True], repeat=6):
            count = sum(bits)
            expected = (count == 1 if method == "auto_eq" else count <= 1) and sum(bits[:3]) == 1 and sum(bits[1:4]) == 1
            assert solver.solve(assumptions=[lit if bit else -lit for lit, bit in zip(lits, bits)]) == expected


def test_nested_model_amos_never_partition(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("nested AMOs entered overlap partitioning")

    monkeypatch.setattr(pbamo, "choose_overlap_partition", reject)
    m = Model()
    bits = m.bool_vector("b", 1024)
    m &= bits.at_most_one()
    m &= bits[0] + bits[1] <= 1
    assert len(m.to_cnf().clauses) < 4200


def test_dynamic_bitsets_match_full_compatibility_checks(monkeypatch):
    original_priority = pbamo._DynamicOverlapPartition._priority
    original_future = pbamo._DynamicOverlapPartition._future_compatibility

    def priority(self, lit):
        expected = sum(pbamo._group_is_compatible(self.neighbors, lit, group) for group in self.groups)
        assert self.compatible_counts[lit] == expected
        return original_priority(self, lit)

    def future(self, lit, group):
        expected = sum(pbamo._group_is_compatible(self.neighbors, other, [*group, lit])
                       for other in self.remaining if other != lit and self.neighbors[other])
        actual = original_future(self, lit, group)
        assert actual == expected
        return actual

    monkeypatch.setattr(pbamo._DynamicOverlapPartition, "_priority", priority)
    monkeypatch.setattr(pbamo._DynamicOverlapPartition, "_future_compatibility", future)
    rng = random.Random(963)
    for _ in range(60):
        lits = [i * rng.choice([-1, 1]) for i in range(1, 21)]
        weights = [rng.randint(1, 20) for _ in lits]
        groups = [rng.sample(lits, 6) for _ in range(12)]
        pbamo.choose_overlap_partition(lits, weights, amo_groups=groups[:8], eo_groups=groups[8:])
