"""Internal bindings for structured PB(AMO) encoders."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from math import gcd

from pysat.formula import CNFPlus

from hermax.internal import _pbamo as _native_pbamo
from hermax.encoder.card import CardEnc, EncType as CardEncType, ITotalizer
from hermax.encoder.pb_enc import PBEnc, EncType as PBEncType
from hermax.internal.kmerge import get_basis, get_conflict_depth, get_short_circuit_subsets


CARD_STRUCTURE_THRESHOLD = 0.27
CARD_FLAT_ENCODING = CardEncType.kmtotalizer


class EncType:
    best = "best"
    mdd = "mdd"
    gswc = "gswc"
    ggpw = "ggpw"
    gmto = "gmto"
    rggt = "rggt"


class OverlapPolicy:
    baseline_paper = "baseline_paper"
    paper_best_fit_dynamic_future = "paper_best_fit_dynamic_future"


def _normalize_groups(groups):
    return [[int(lit) for lit in group] for group in groups]


def _normalize_candidate_groups(groups: Iterable[Iterable[int]] | None):
    if not groups:
        return []
    out = []
    for group in groups:
        uniq = []
        seen = set()
        for lit in group:
            lit_i = int(lit)
            if lit_i in seen:
                continue
            seen.add(lit_i)
            uniq.append(lit_i)
        if uniq:
            out.append(uniq)
    return out


def _pair_support_maps(lits, amo_groups, eo_groups):
    pair_support: dict[tuple[int, int], int] = {}
    eo_pair_support: dict[tuple[int, int], int] = {}
    mutex_neighbors = {int(lit): set() for lit in lits}

    def _add_group_support(group, target):
        for i in range(len(group)):
            li = int(group[i])
            for j in range(i + 1, len(group)):
                lj = int(group[j])
                key = (li, lj) if li < lj else (lj, li)
                target[key] = target.get(key, 0) + 1
                mutex_neighbors[li].add(lj)
                mutex_neighbors[lj].add(li)

    for group in amo_groups:
        _add_group_support(group, pair_support)
    for group in eo_groups:
        _add_group_support(group, pair_support)
        _add_group_support(group, eo_pair_support)

    return pair_support, eo_pair_support, mutex_neighbors


def _pair_score(pair_map, a: int, b: int) -> int:
    if a == b:
        return 0
    key = (a, b) if a < b else (b, a)
    return int(pair_map.get(key, 0))


def _group_is_compatible(mutex_neighbors, lit: int, group) -> bool:
    neighbors = mutex_neighbors.get(int(lit), set())
    return all(int(member) in neighbors for member in group)


def _partition_score(grouping):
    normalized = [tuple(sorted(int(l) for l in group)) for group in grouping if group]
    normalized.sort(key=lambda g: (len(g), g))
    return tuple(normalized)


def _disjoint_candidate_partition(lits, weights, amo_groups, eo_groups, policy):
    """Reuse disjoint cliques without changing the existing partition order."""
    positions = {lit: i for i, lit in enumerate(lits)}
    if len(positions) != len(lits):
        return None
    owners, counts = {}, {}
    for is_eo, candidates in ((False, amo_groups), (True, eo_groups)):
        for group in candidates:
            members = frozenset(group)
            if len(members) < 2:
                continue
            if members not in counts:
                if not members <= positions.keys() or any(lit in owners for lit in members):
                    return None
                counts[members] = [0, 0]
                owners.update((lit, members) for lit in members)
            counts[members][0] += 1
            counts[members][1] += is_eo
    counts.update((frozenset([lit]), [0, 0]) for lit in lits if lit not in owners)

    def priority(members):
        if policy == OverlapPolicy.baseline_paper:
            return min(positions[lit] for lit in members)
        # Each clique starts before the greedy algorithm fills existing cliques.
        degree = len(members) - 1
        pair_count, eo_count = counts[members]
        first = min(members, key=lambda lit: (-weights[lit], lit))
        return (-eo_count * degree, -pair_count * degree, -degree, -weights[first], first)

    return [sorted(group) for group in sorted(counts, key=priority)]


def choose_overlap_partition(
    lits,
    weights,
    *,
    amo_groups=None,
    eo_groups=None,
    policy: str = OverlapPolicy.paper_best_fit_dynamic_future,
):
    lits = [int(lit) for lit in lits]
    weight_by_lit = {int(lit): int(weight) for lit, weight in zip(lits, weights)}
    amo_groups = _normalize_candidate_groups(amo_groups)
    eo_groups = _normalize_candidate_groups(eo_groups)
    if policy not in {OverlapPolicy.baseline_paper, OverlapPolicy.paper_best_fit_dynamic_future}:
        raise ValueError(f"Unknown overlap policy: {policy!r}")
    partition = _disjoint_candidate_partition(lits, weight_by_lit, amo_groups, eo_groups, policy)
    if partition is not None:
        return partition
    pair_support, eo_pair_support, mutex_neighbors = _pair_support_maps(lits, amo_groups, eo_groups)
    if policy == OverlapPolicy.baseline_paper:
        return _baseline_overlap_partition(lits, mutex_neighbors)
    return _DynamicOverlapPartition(
        lits, weight_by_lit, pair_support, eo_pair_support, mutex_neighbors,
    ).partition()


def _baseline_overlap_partition(lits, mutex_neighbors):
    groups: list[list[int]] = []
    for lit in lits:
        if mutex_neighbors[lit]:
            for group in groups:
                if _group_is_compatible(mutex_neighbors, lit, group):
                    group.append(lit)
                    break
            else:
                groups.append([lit])
        else:
            groups.append([lit])
    return [sorted(group) for group in groups]


class _DynamicOverlapPartition:
    """Per-call state for the existing greedy policy; no cross-call cache."""

    def __init__(self, lits, weights, pair_support, eo_support, neighbors):
        self.weights = weights
        self.pair_support = pair_support
        self.eo_support = eo_support
        self.neighbors = neighbors
        self.groups: list[list[int]] = []
        self.remaining = set(lits)
        # These degrees never depend on the evolving groups or remaining set.
        # Multiplicity preserves the old score even for repeated input literals.
        counts = Counter(lits)
        self.pair_degrees = self._support_degrees(pair_support, counts)
        self.eo_degrees = self._support_degrees(eo_support, counts)

    def _support_degrees(self, support, counts):
        return {
            lit: sum(_pair_score(support, lit, other) * counts[other] for other in self.neighbors[lit])
            for lit in self.remaining
        }

    def _priority(self, lit):
        compatible_count = 0
        if self.neighbors[lit]:
            compatible_count = sum(
                _group_is_compatible(self.neighbors, lit, group) for group in self.groups
            )
        return (
            compatible_count, -self.eo_degrees[lit], -self.pair_degrees[lit],
            -len(self.neighbors[lit]), -self.weights[lit], lit,
        )

    def _future_compatibility(self, lit, group):
        proposed = [*group, lit]
        return sum(
            _group_is_compatible(self.neighbors, other, proposed)
            for other in self.remaining if other != lit and self.neighbors[other]
        )

    def _group_score(self, lit, group):
        candidate_weights = [self.weights[member] for member in group] + [self.weights[lit]]
        return (
            sum(_pair_score(self.eo_support, lit, member) for member in group),
            sum(_pair_score(self.pair_support, lit, member) for member in group),
            self._future_compatibility(lit, group),
            len(group),
            -(max(candidate_weights) - min(candidate_weights)),
            sum(candidate_weights),
            -min(group),
        )

    def partition(self):
        while self.remaining:
            lit = min(self.remaining, key=self._priority)
            compatible = []
            if self.neighbors[lit]:
                compatible = [
                    group for group in self.groups
                    if _group_is_compatible(self.neighbors, lit, group)
                ]
            if compatible:
                best = max(compatible, key=lambda group: self._group_score(lit, group))
                best.append(lit)
            else:
                self.groups.append([lit])
            self.remaining.remove(lit)
        return [sorted(group) for group in self.groups]


def amo_upper_bound(weights, groups, lits=None) -> int:
    if lits is None:
        lits = list(range(1, len(weights) + 1))
    weight_by_lit = {int(lit): int(weight) for lit, weight in zip(lits, weights)}
    return sum(max(weight_by_lit[lit] for lit in group) for group in groups)


def extract_features(lits, weights, groups, bound):
    lits = [int(lit) for lit in lits]
    weights = [int(weight) for weight in weights]
    groups = _normalize_groups(groups)
    n_terms = len(lits)
    amo_cap = amo_upper_bound(weights, groups, lits=lits) if groups else 0
    return {
        "n_terms": float(n_terms),
        "n_groups": float(len(groups)),
        "bound_ratio_amo": (float(bound) / float(amo_cap)) if amo_cap > 0 else 0.0,
    }


def extract_cardinality_features(lits, groups, bound):
    lits = [int(lit) for lit in lits]
    groups = _normalize_groups(groups)
    n_terms = len(lits)
    non_singleton = [group for group in groups if len(group) > 1]
    covered = sum(len(group) for group in non_singleton)
    structured_coverage = (float(covered) / float(n_terms)) if n_terms > 0 else 0.0
    mutex_degree_sum = sum((len(group) - 1) * len(group) for group in non_singleton)
    mean_mutex_degree = (float(mutex_degree_sum) / float(n_terms)) if n_terms > 0 else 0.0
    amo_cap = float(len(groups)) if groups else 0.0
    amo_upper_bound_ratio = (float(bound) / amo_cap) if amo_cap > 0.0 else 0.0
    card_structure_score = structured_coverage * (1.0 + mean_mutex_degree) * (amo_upper_bound_ratio ** 0.5)
    return {
        "n_terms": float(n_terms),
        "n_groups": float(len(groups)),
        "non_singleton_groups": float(len(non_singleton)),
        "structured_coverage": structured_coverage,
        "mean_mutex_degree": mean_mutex_degree,
        "amo_upper_bound_ratio": amo_upper_bound_ratio,
        "card_structure_score": card_structure_score,
    }


def choose_portfolio(lits, weights, groups, bound):
    lits = [int(lit) for lit in lits]
    weights = [int(weight) for weight in weights]
    groups = _normalize_groups(groups)
    non_singleton_groups = sum(1 for group in groups if len(group) > 1)
    if non_singleton_groups == 0:
        return "pblib"
    n_terms = len(lits)
    if n_terms <= 11:
        return "pblib"
    amo_cap = amo_upper_bound(weights, groups, lits=lits) if groups else 0
    if amo_cap > 3596:
        return "pblib"
    return "pbamo"


def choose_cardinality_portfolio(lits, groups, bound):
    n_terms = len(lits)
    features = extract_cardinality_features(lits, groups, bound)
    if n_terms <= 11:
        return "card"
    if features["non_singleton_groups"] == 0.0:
        return "card"
    amo_cap = features["n_groups"]
    card_score = features["card_structure_score"]
    structured_coverage = features["structured_coverage"]

    decision = "card"
    if amo_cap <= 46.5 and card_score > 0.235817:
        if amo_cap <= 31.5:
            decision = "pbamo"
        elif structured_coverage > 0.591751:
            decision = "pbamo"

    if decision == "pbamo":
        if n_terms >= 45 and amo_cap >= 22.0:
            return "card"
        if n_terms >= 40 and card_score < 1.0:
            return "card"
        return "pbamo"
    return "card"


def choose_encoding(lits, weights, groups, bound):
    """Select an encoder with a fitted, propagation-weighted depth-three tree.

    The fit counts GGPW's sizes twice to favor the stronger propagation of
    MDD, GSWC and RGGT. Every leaf selects an encoder directly.
    """
    weights = [int(weight) for weight in weights]
    groups = _normalize_groups(groups)
    reduced_bound = int(bound) // (gcd(*weights) or 1)

    if len(groups) <= 24:
        if reduced_bound <= 2:
            return EncType.gswc
        if sum(len(group) > 1 for group in groups) <= 11:
            return EncType.mdd
        return EncType.rggt

    # Compare the mean with the fitted threshold 15.171875 (= 971/64)
    # using integer arithmetic, including at the exact boundary.
    if 64 * sum(weights) <= 971 * len(weights):
        return EncType.rggt if reduced_bound <= 95 else EncType.mdd
    return EncType.ggpw


@dataclass(frozen=True)
class _PreparedStructure:
    """Owned, immutable grouping data reused only within one encoding call.

    The selected partition is an encoding aid. The original overlapping
    candidates must still be emitted, even when absent from that partition.
    """

    groups: tuple[tuple[int, ...], ...]
    amo_groups: tuple[tuple[int, ...], ...]
    eo_groups: tuple[tuple[int, ...], ...]

    def append_candidate_clauses(self, cnf: CNFPlus, card_encoder) -> None:
        for group in self.amo_groups + self.eo_groups:
            ordered = sorted(set(group))
            if len(ordered) < 32:
                for lit, other in combinations(ordered, 2):
                    cnf.clauses.append([-lit, -other])
            else:
                encoded = card_encoder.atmost(
                    lits=ordered, bound=1, top_id=cnf.nv, encoding=CardEncType.ladder,
                )
                cnf.clauses.extend(encoded.clauses)
                cnf.nv = max(cnf.nv, encoded.nv)
        for group in self.eo_groups:
            ordered = sorted(set(group))
            if ordered:
                cnf.clauses.append(ordered)


class PBAMOEnc:
    _new_cnf = CNFPlus
    _pb_encoder = PBEnc
    _card_encoder = CardEnc
    _totalizer = ITotalizer

    @staticmethod
    def _encode_leq_native(**kwargs):
        return _native_pbamo.encode_leq(**kwargs)

    @staticmethod
    def _encode_eq_native(**kwargs):
        return _native_pbamo.encode_eq(**kwargs)

    @staticmethod
    def _validate_pb_input(lits, weights, bound) -> None:
        if len(lits) != len(weights):
            raise ValueError("Same number of literals and weights is expected.")
        if isinstance(bound, bool) or not isinstance(bound, int):
            raise ValueError("PB bound must be an integer.")
        if any(isinstance(lit, bool) or not isinstance(lit, int) or lit == 0 for lit in lits):
            raise ValueError("PB literals must be non-zero integers.")
        if any(isinstance(weight, bool) or not isinstance(weight, int) for weight in weights):
            raise ValueError("PB weights must be integers.")
        if any(weight < 0 for weight in weights):
            raise ValueError("PB weights must be non-negative.")

    @staticmethod
    def _validate_partition_groups(lits, groups) -> None:
        """Check explicit structured-PB groups before calling the native layer."""
        expected = list(lits)
        seen: list[int] = []
        for group in groups:
            if not group:
                raise ValueError("PBAMO groups must be non-empty.")
            for lit in group:
                if isinstance(lit, bool) or not isinstance(lit, int) or lit == 0:
                    raise ValueError("PBAMO group literals must be non-zero integers.")
                seen.append(lit)
        if len(seen) != len(expected) or set(seen) != set(expected) or len(set(seen)) != len(seen):
            raise ValueError("PBAMO groups must form a duplicate-free partition of the PB literals.")

    @classmethod
    def multi_leq(cls, lits, stubs, top_id, kmerge_config=None):
        """Encode multiple PB constraints using a shared basis sum.
        
        Args:
            lits: The literal core (ordered dimacs IDs).
            stubs: List of PBConstraintStub (weights, bound, op).
            top_id: The current top variable ID.
        """

        for stub in stubs:
            cls._validate_pb_input(lits, stub.weights, stub.bound)
            if tuple(stub.lits) != tuple(lits):
                raise ValueError("PB constraint stub literals must align with the shared literal core.")
            if stub.op not in ("<=", "=="):
                raise ValueError(f"Unsupported PB comparison: {stub.op!r}")
        
        cnf = cls._new_cnf()
        cnf.nv = int(top_id)

        # A constant PB constraint must be resolved before building the shared
        # basis.  In particular, ``max([])`` is undefined and PBLib rejects a
        # negative bound on an empty sum even when that simply means UNSAT.
        active_stubs = []
        for stub in stubs:
            if any(stub.weights):
                active_stubs.append(stub)
                continue
            satisfied = 0 <= int(stub.bound) if stub.op == "<=" else 0 == int(stub.bound)
            if not satisfied:
                cnf.clauses.append([])
                return cnf
        if not active_stubs:
            return cnf

        stubs = active_stubs
        weights_list = [s.weights for s in stubs]
        basis = get_basis(weights_list, config=kmerge_config)
        
        # 1. Decompose basis into bit columns and encode with Totalizers
        max_b = max(basis)
        num_bits = max_b.bit_length()
        
        # Column outputs: col_bits[bit_idx] = list of unary bits representing the count
        col_bits = []
        for b_idx in range(num_bits):
            mask = 1 << b_idx
            active_lits = [lit for i, lit in enumerate(lits) if basis[i] & mask]
            if not active_lits:
                col_bits.append([])
                continue
                
            # Use Totalizer for the column
            tot = cls._totalizer(lits=active_lits, ubound=len(active_lits), top_id=cnf.nv)
            cnf.clauses.extend(tot.cnf.clauses)
            cnf.nv = max(cnf.nv, tot.cnf.nv)
            # tot.rhs[k] corresponds to 'sum >= k+1'
            col_bits.append(tot.rhs)

        # 2. Build a carry adder for the Basis Sum
        # Binary representation of basis sum: basis_out[idx] is bit with weight 2^idx
        basis_out = []
        carry_bits = [] # bits to be added to the next column
        
        # Continue until every source column and every generated carry has
        # been consumed. A fixed overflow allowance is unsound for wide
        # unary columns.
        b_idx = 0
        while b_idx < num_bits or carry_bits:
            current_inputs = []
            if b_idx < len(col_bits):
                current_inputs.extend(col_bits[b_idx])
            current_inputs.extend(carry_bits)
            carry_bits = []
            
            if not current_inputs:
                basis_out.append(0)
                b_idx += 1
                continue
            
            # Simple Full Adder reduction of current_inputs
            while len(current_inputs) > 2:
                # FA(a, b, c) -> (sum, carry)
                a, b, c = current_inputs.pop(), current_inputs.pop(), current_inputs.pop()
                cnf.nv += 2
                s_bit, c_bit = cnf.nv - 1, cnf.nv
                
                # FA Clauses:
                # Sum bit: s <-> a^b^c
                for combo in [(1,1,1), (1,-1,-1), (-1,1,-1), (-1,-1,1)]:
                    cnf.clauses.append([-combo[0]*a, -combo[1]*b, -combo[2]*c, s_bit])
                    cnf.clauses.append([combo[0]*a, combo[1]*b, combo[2]*c, -s_bit])
                
                # Carry bit: c_out <-> (a&b)|(b&c)|(a&c)
                cnf.clauses.append([-a, -b, c_bit])
                cnf.clauses.append([-a, -c, c_bit])
                cnf.clauses.append([-b, -c, c_bit])
                cnf.clauses.append([a, b, -c_bit])
                cnf.clauses.append([a, c, -c_bit])
                cnf.clauses.append([b, c, -c_bit])
                
                current_inputs.append(s_bit)
                carry_bits.append(c_bit)
            
            if len(current_inputs) == 2:
                # Half Adder: a+b -> (sum, carry)
                a, b = current_inputs.pop(), current_inputs.pop()
                cnf.nv += 2
                s_bit, c_bit = cnf.nv - 1, cnf.nv
                # s <-> a^b
                cnf.clauses.append([-a, -b, -s_bit])
                cnf.clauses.append([a, b, -s_bit])
                cnf.clauses.append([-a, b, s_bit])
                cnf.clauses.append([a, -b, s_bit])
                # c <-> a&b
                cnf.clauses.append([-a, -b, c_bit])
                cnf.clauses.append([a, -c_bit])
                cnf.clauses.append([b, -c_bit])
                
                basis_out.append(s_bit)
                carry_bits.append(c_bit)
            elif len(current_inputs) == 1:
                basis_out.append(current_inputs.pop())
            else:
                basis_out.append(0)

            b_idx += 1

        # 3. Encode each constraint's Delta part
        for stub in stubs:
            delta_weights = [ stub.weights[i] - basis[i] for i in range(len(lits)) ]

            if (
                kmerge_config is not None
                and kmerge_config.use_slack_tripwire
                and kmerge_config.use_short_circuit_penalty
            ):
                max_basis = sum(basis)
                if max_basis > int(stub.bound):
                    conflict_depth = get_conflict_depth(basis, int(stub.bound))
                    abort_depth = int(kmerge_config.slack_conflict_depth_abort)
                    if conflict_depth is not None and conflict_depth < abort_depth:
                        for subset in get_short_circuit_subsets(basis, int(stub.bound), conflict_depth):
                            cnf.clauses.append([-int(lits[idx]) for idx in subset])
            
            # Final sum = S_basis + S_delta
            # Inputs to final encoder: BasisBits (weights 2^j) + DeltaLits (weights delta_w_i)
            final_lits = []
            final_weights = []
            
            for j, b_bit in enumerate(basis_out):
                if b_bit != 0:
                    final_lits.append(b_bit)
                    final_weights.append(1 << j)
            
            for i, d_w in enumerate(delta_weights):
                if d_w > 0:
                    final_lits.append(lits[i])
                    final_weights.append(d_w)
            
            # The shared basis circuit is a sound upper-bound encoding. An
            # equality additionally needs a lower bound, but encoding equality
            # directly over the shared binary sum is unsound. Keep the shared
            # upper bound and add only the missing direct lower bound.
            if stub.op not in ("<=", "=="):
                raise ValueError(f"Unsupported PB comparison: {stub.op!r}")
            sub_cnf = cls._pb_encoder.leq(
                lits=final_lits,
                weights=final_weights,
                bound=stub.bound,
                top_id=cnf.nv,
                encoding=PBEncType.adder,
            )
            
            cnf.clauses.extend(sub_cnf.clauses)
            cnf.nv = max(cnf.nv, sub_cnf.nv)

            if stub.op == "==":
                lower_cnf = cls._pb_encoder.geq(
                    lits=list(lits),
                    weights=list(stub.weights),
                    bound=stub.bound,
                    top_id=cnf.nv,
                    encoding=PBEncType.adder,
                )
                cnf.clauses.extend(lower_cnf.clauses)
                cnf.nv = max(cnf.nv, lower_cnf.nv)
            
        return cnf

    @classmethod
    def leq(cls, lits, weights, groups, bound, top_id=None, encoding=EncType.best, emit_amo=True):
        cls._validate_pb_input(lits, weights, bound)
        cls._validate_partition_groups(lits, groups)
        wlits = [(int(lit), int(weight)) for lit, weight in zip(lits, weights)]
        grouped = _normalize_groups(groups)
        if top_id is None:
            top_id = max((abs(int(lit)) for lit in lits), default=0)
        if encoding == EncType.best:
            encoding = choose_encoding(lits, weights, grouped, bound)
        clauses, max_aux = cls._encode_leq_native(
            wlits=wlits,
            groups=grouped,
            bound=int(bound),
            top_id=int(top_id),
            encoder=str(encoding),
            emit_amo=bool(emit_amo),
        )
        cnf = cls._new_cnf()
        cnf.clauses = clauses
        cnf.nv = max(int(top_id), int(max_aux))
        return cnf

    @classmethod
    def equals(cls, lits, weights, groups, bound, top_id=None, encoding=EncType.rggt, emit_amo=True):
        """Encode a grouped equality with one shared RGGT sum tree.

        With ``emit_amo=False``, callers must enforce the supplied AMO groups.
        This explicit path does not change the routing of ``auto_eq``.
        """
        cls._validate_pb_input(lits, weights, bound)
        cls._validate_partition_groups(lits, groups)
        if encoding != EncType.rggt:
            raise ValueError("Native equality is supported only by the rggt encoder.")
        if top_id is None:
            top_id = max(map(abs, lits), default=0)
        clauses, nv = cls._encode_eq_native(
            wlits=list(zip(lits, weights)), groups=_normalize_groups(groups),
            bound=bound, top_id=int(top_id), encoder=encoding, emit_amo=bool(emit_amo),
        )
        cnf = cls._new_cnf()
        cnf.clauses = clauses
        cnf.nv = int(nv)
        return cnf

    @classmethod
    def _prepare_structure(cls, lits, weights, groups, amo_groups, eo_groups, policy) -> _PreparedStructure:
        """Normalize candidates and choose their partition once per encoding."""
        partition = _normalize_groups(groups) if groups is not None else None
        if partition is not None:
            cls._validate_partition_groups(lits, partition)
        amo = _normalize_candidate_groups(amo_groups)
        eo = _normalize_candidate_groups(eo_groups)
        if partition is not None and (amo or eo):
            raise ValueError("Provide either disjoint groups or overlapping AMO/EO candidates, not both.")
        if partition is None:
            partition = (
                choose_overlap_partition(lits, weights, amo_groups=amo, eo_groups=eo, policy=policy)
                if amo or eo else [[lit] for lit in lits]
            )
        return _PreparedStructure(
            tuple(map(tuple, partition)), tuple(map(tuple, amo)), tuple(map(tuple, eo)),
        )

    @classmethod
    def auto_leq(
        cls,
        *,
        lits,
        weights,
        bound,
        groups=None,
        amo_groups=None,
        eo_groups=None,
        top_id=None,
        overlap_policy: str = OverlapPolicy.paper_best_fit_dynamic_future,
        structured_encoding=EncType.best,
    ):
        cls._validate_pb_input(lits, weights, bound)
        lits = [int(lit) for lit in lits]
        weights = [int(weight) for weight in weights]
        structure = cls._prepare_structure(lits, weights, groups, amo_groups, eo_groups, overlap_policy)
        top_id = int(top_id) if top_id is not None else max(map(abs, lits), default=0)
        return cls._encode_leq_prepared(lits, weights, bound, top_id, structure, structured_encoding)

    @classmethod
    def _encode_leq_prepared(cls, lits, weights, bound, top_id, structure, structured_encoding):
        """Encode the upper inequality without repeating structural analysis."""
        if all(weight == 1 for weight in weights):
            return cls._encode_atmost_prepared(
                lits, bound, top_id, structure, structured_encoding, CARD_FLAT_ENCODING,
            )

        if choose_portfolio(lits, weights, structure.groups, bound) == "pblib":
            cnf = cls._pb_encoder.leq(lits=lits, weights=weights, bound=bound, top_id=top_id, encoding=PBEncType.best)
        else:
            enc = structured_encoding
            if enc == EncType.best:
                enc = choose_encoding(lits, weights, structure.groups, bound)
            cnf = cls.leq(
                lits=lits, weights=weights, groups=structure.groups, bound=bound,
                top_id=top_id, encoding=enc, emit_amo=False,
            )
        structure.append_candidate_clauses(cnf, cls._card_encoder)
        cnf.nv = max(int(cnf.nv), top_id)
        return cnf

    @classmethod
    def auto_eq(
        cls,
        *,
        lits,
        weights,
        bound,
        groups=None,
        amo_groups=None,
        eo_groups=None,
        top_id=None,
        overlap_policy: str = OverlapPolicy.paper_best_fit_dynamic_future,
        structured_encoding=EncType.best,
    ):
        cls._validate_pb_input(lits, weights, bound)
        lits = [int(lit) for lit in lits]
        weights = [int(weight) for weight in weights]
        structure = cls._prepare_structure(lits, weights, groups, amo_groups, eo_groups, overlap_policy)
        top_id = int(top_id) if top_id is not None else max(map(abs, lits), default=0)

        total_weight = sum(weights)
        if bound < 0 or bound > total_weight:
            cnf = cls._new_cnf()
            cnf.nv = top_id
            cnf.clauses.append([])
            return cnf

        # No structural signal: keep the stronger dedicated equals backend.
        has_structure = any(len(group) > 1 for group in structure.groups)
        if not has_structure and not structure.amo_groups and not structure.eo_groups:
            if all(weight == 1 for weight in weights):
                encoding = CardEncType.ladder if bound in (1, len(lits) - 1) else CARD_FLAT_ENCODING
                return cls._card_encoder.equals(lits=lits, bound=bound, top_id=top_id, encoding=encoding)

            return cls._pb_encoder.equals(lits=lits, weights=weights, bound=bound, top_id=top_id, encoding=PBEncType.best)

        return cls._encode_eq_prepared(
            lits, weights, bound, top_id, structure, overlap_policy, structured_encoding,
        )

    @classmethod
    def _encode_eq_prepared(cls, lits, weights, bound, top_id, structure, overlap_policy, structured_encoding):
        upper = cls._encode_leq_prepared(lits, weights, bound, top_id, structure, structured_encoding)
        # Original AMO/EO candidates apply only to the direct upper side.
        # Negating them for the lower side is unsound, particularly for EO.
        lower = cls.auto_leq(
            lits=[-lit for lit in lits], weights=weights, bound=sum(weights) - bound,
            top_id=max(top_id, int(upper.nv)), overlap_policy=overlap_policy,
            structured_encoding=structured_encoding,
        )
        cnf = cls._new_cnf()
        cnf.clauses.extend(upper.clauses)
        cnf.clauses.extend(lower.clauses)
        cnf.nv = max(int(upper.nv), int(lower.nv), top_id)
        return cnf

    @classmethod
    def _auto_atmost(
        cls,
        *,
        lits,
        bound,
        groups=None,
        amo_groups=None,
        eo_groups=None,
        top_id=None,
        overlap_policy: str = OverlapPolicy.paper_best_fit_dynamic_future,
        structured_encoding=EncType.best,
        flat_encoding=CARD_FLAT_ENCODING,
    ):
        lits = [int(lit) for lit in lits]
        structure = cls._prepare_structure(lits, [1] * len(lits), groups, amo_groups, eo_groups, overlap_policy)
        top_id = int(top_id) if top_id is not None else max(map(abs, lits), default=0)
        return cls._encode_atmost_prepared(lits, int(bound), top_id, structure, structured_encoding, flat_encoding)

    @classmethod
    def _encode_atmost_prepared(cls, lits, bound, top_id, structure, structured_encoding, flat_encoding):
        if choose_cardinality_portfolio(lits, structure.groups, bound) == "card":
            if bound == 1 and flat_encoding == CardEncType.kmtotalizer:
                flat_encoding = CardEncType.ladder
            cnf = cls._card_encoder.atmost(lits=lits, bound=bound, top_id=top_id, encoding=flat_encoding)
        else:
            enc = structured_encoding
            if enc == EncType.best:
                enc = choose_encoding(lits, [1] * len(lits), structure.groups, bound)
            cnf = cls.leq(
                lits=lits, weights=[1] * len(lits), groups=structure.groups,
                bound=bound, top_id=top_id, encoding=enc, emit_amo=False,
            )
        structure.append_candidate_clauses(cnf, cls._card_encoder)
        cnf.nv = max(int(cnf.nv), top_id)
        return cnf


def available_encoders():
    return [EncType.best, *_native_pbamo.available_encoders()]


__all__ = [
    "CARD_FLAT_ENCODING",
    "CARD_STRUCTURE_THRESHOLD",
    "EncType",
    "OverlapPolicy",
    "PBAMOEnc",
    "amo_upper_bound",
    "available_encoders",
    "choose_cardinality_portfolio",
    "choose_encoding",
    "choose_overlap_partition",
    "choose_portfolio",
    "extract_cardinality_features",
    "extract_features",
]
