"""Internal bindings for structured PB(AMO) encoders."""

from __future__ import annotations

from collections.abc import Iterable

from pysat.formula import CNFPlus

from hermax.internal import _pbamo as _native_pbamo
from hermax.encoder.card import CardEnc, EncType as CardEncType


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
    pair_support, eo_pair_support, mutex_neighbors = _pair_support_maps(lits, amo_groups, eo_groups)

    if policy not in {OverlapPolicy.baseline_paper, OverlapPolicy.paper_best_fit_dynamic_future}:
        raise ValueError(f"Unknown overlap policy: {policy!r}")

    groups: list[list[int]] = []

    if policy == OverlapPolicy.baseline_paper:
        for lit in lits:
            placed = False
            for group in groups:
                if _group_is_compatible(mutex_neighbors, lit, group):
                    group.append(int(lit))
                    placed = True
                    break
            if not placed:
                groups.append([int(lit)])
        return [sorted(group) for group in groups]

    remaining = set(lits)

    def compatible_groups_count(lit: int) -> int:
        return sum(1 for group in groups if _group_is_compatible(mutex_neighbors, lit, group))

    def eo_support_degree(lit: int) -> int:
        return sum(_pair_score(eo_pair_support, lit, other) for other in lits if other != lit)

    def pair_support_degree(lit: int) -> int:
        return sum(_pair_score(pair_support, lit, other) for other in lits if other != lit)

    def future_compatibility(lit: int, group) -> int:
        proposed = [*group, int(lit)]
        total = 0
        for other in remaining:
            if other == lit:
                continue
            if _group_is_compatible(mutex_neighbors, other, proposed):
                total += 1
        return total

    while remaining:
        lit = min(
            remaining,
            key=lambda cur: (
                compatible_groups_count(cur),
                -eo_support_degree(cur),
                -pair_support_degree(cur),
                -len(mutex_neighbors.get(cur, set())),
                -weight_by_lit[cur],
                cur,
            ),
        )
        compatible = [group for group in groups if _group_is_compatible(mutex_neighbors, lit, group)]
        if not compatible:
            groups.append([int(lit)])
            remaining.remove(lit)
            continue

        def score_group(group):
            eo_support = sum(_pair_score(eo_pair_support, lit, member) for member in group)
            support = sum(_pair_score(pair_support, lit, member) for member in group)
            future = future_compatibility(lit, group)
            candidate_weights = [weight_by_lit[member] for member in group] + [weight_by_lit[lit]]
            spread = max(candidate_weights) - min(candidate_weights)
            return (
                eo_support,
                support,
                future,
                len(group),
                -spread,
                sum(candidate_weights),
                -min(group),
            )

        best = max(compatible, key=score_group)
        best.append(int(lit))
        remaining.remove(lit)

    return [sorted(group) for group in groups]


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
    lits = [int(lit) for lit in lits]
    weights = [int(weight) for weight in weights]
    groups = _normalize_groups(groups)
    n_terms = float(len(lits))
    n_groups = float(len(groups))
    amo_cap = float(amo_upper_bound(weights, groups, lits=lits)) if groups else 0.0
    non_singleton_groups = float(sum(1 for group in groups if len(group) > 1))

    if n_terms <= 35.5:
        if amo_cap > 4381.0:
            return EncType.ggpw
        if amo_cap > 477.5 and non_singleton_groups > 8.5:
            return EncType.ggpw
        return EncType.rggt

    if amo_cap <= 222.5:
        return EncType.rggt
    if n_groups <= 7.5:
            return EncType.rggt
    return EncType.ggpw


class PBAMOEnc:
    @classmethod
    def multi_leq(cls, lits, stubs, top_id, kmerge_config=None):
        """Encode multiple PB constraints using a shared basis sum.
        
        Args:
            lits: The literal core (ordered dimacs IDs).
            stubs: List of PBConstraintStub (weights, bound, op).
            top_id: The current top variable ID.
        """
        from hermax.internal.kmerge import get_basis, get_conflict_depth, get_short_circuit_subsets
        from hermax.encoder.card import ITotalizer
        from hermax.encoder.pb_enc import PBEnc, EncType as PBEncType
        
        cnf = CNFPlus()
        cnf.nv = int(top_id)
        
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
            tot = ITotalizer(lits=active_lits, ubound=len(active_lits), top_id=cnf.nv)
            cnf.clauses.extend(tot.cnf.clauses)
            cnf.nv = max(cnf.nv, tot.cnf.nv)
            # tot.rhs[k] corresponds to 'sum >= k+1'
            col_bits.append(tot.rhs)

        # 2. Build a carry adder for the Basis Sum
        # Binary representation of basis sum: basis_out[idx] is bit with weight 2^idx
        basis_out = []
        carry_bits = [] # bits to be added to the next column
        
        # We process column by column. carry_bits contains literals with weight 1 for CURRENT column.
        for b_idx in range(num_bits + 10): # +10 for overflow carries
            current_inputs = []
            if b_idx < len(col_bits):
                current_inputs.extend(col_bits[b_idx])
            current_inputs.extend(carry_bits)
            carry_bits = []
            
            if not current_inputs:
                if b_idx >= len(col_bits): break
                basis_out.append(0)
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

        # 3. Encode each constraint's Delta part
        for stub in stubs:
            delta_weights = [ stub.weights[i] - basis[i] for i in range(len(lits)) ]

            if (
                kmerge_config is not None
                and bool(getattr(kmerge_config, "use_slack_tripwire", False))
                and bool(getattr(kmerge_config, "use_short_circuit_penalty", False))
            ):
                max_basis = sum(basis)
                if max_basis > int(stub.bound):
                    conflict_depth = get_conflict_depth(basis, int(stub.bound))
                    abort_depth = int(getattr(kmerge_config, "slack_conflict_depth_abort", 4))
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
            
            # Encode final LEQ/EQ
            if stub.op == "<=":
                sub_cnf = PBEnc.leq(lits=final_lits, weights=final_weights, bound=stub.bound, top_id=cnf.nv, encoding=PBEncType.adder)
            else: # "=="
                sub_cnf = PBEnc.equals(lits=final_lits, weights=final_weights, bound=stub.bound, top_id=cnf.nv, encoding=PBEncType.adder)
                if stub.bound == 1 and all(w == 1 for w in stub.weights):
                    cnf.clauses.append(list(lits))
            
            cnf.clauses.extend(sub_cnf.clauses)
            cnf.nv = max(cnf.nv, sub_cnf.nv)
            
        return cnf

    @classmethod
    def leq(cls, lits, weights, groups, bound, top_id=None, encoding=EncType.best, emit_amo=True):
        if len(lits) != len(weights):
            raise ValueError("Same number of literals and weights is expected.")
        wlits = [(int(lit), int(weight)) for lit, weight in zip(lits, weights)]
        grouped = _normalize_groups(groups)
        if top_id is None:
            top_id = max((abs(int(lit)) for lit in lits), default=0)
        if encoding == EncType.best:
            encoding = choose_encoding(lits, weights, grouped, bound)
        clauses, max_aux = _native_pbamo.encode_leq(
            wlits=wlits,
            groups=grouped,
            bound=int(bound),
            top_id=int(top_id),
            encoder=str(encoding),
            emit_amo=bool(emit_amo),
        )
        cnf = CNFPlus()
        cnf.clauses = clauses
        cnf.nv = max(int(top_id), int(max_aux))
        return cnf

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
        if len(lits) != len(weights):
            raise ValueError("Same number of literals and weights is expected.")
        lits = [int(lit) for lit in lits]
        weights = [int(weight) for weight in weights]
        groups_were_explicit = groups is not None
        normalized_groups = _normalize_groups(groups) if groups is not None else None
        normalized_amo = _normalize_candidate_groups(amo_groups)
        normalized_eo = _normalize_candidate_groups(eo_groups)

        if normalized_groups is not None and (normalized_amo or normalized_eo):
            raise ValueError("Provide either disjoint groups or overlapping AMO/EO candidates, not both.")

        if normalized_groups is None:
            if normalized_amo or normalized_eo:
                normalized_groups = choose_overlap_partition(
                    lits,
                    weights,
                    amo_groups=normalized_amo,
                    eo_groups=normalized_eo,
                    policy=overlap_policy,
                )
            else:
                normalized_groups = [[lit] for lit in lits]

        if top_id is None:
            top_id = max((abs(int(lit)) for lit in lits), default=0)
        top_id = int(top_id)

        if all(int(weight) == 1 for weight in weights):
            return cls._auto_atmost(
                lits=lits,
                bound=int(bound),
                groups=normalized_groups if groups_were_explicit else None,
                amo_groups=normalized_amo if not groups_were_explicit else None,
                eo_groups=normalized_eo if not groups_were_explicit else None,
                top_id=top_id,
                overlap_policy=overlap_policy,
                structured_encoding=structured_encoding,
            )

        portfolio = choose_portfolio(lits, weights, normalized_groups, bound)
        if portfolio == "pblib":
            from hermax.encoder.pb_enc import EncType as PBEncType
            from hermax.encoder.pb_enc import PBEnc

            cnf = PBEnc.leq(lits=lits, weights=weights, bound=int(bound), top_id=top_id, encoding=PBEncType.best)
        else:
            enc = structured_encoding
            if enc == EncType.best:
                enc = choose_encoding(lits, weights, normalized_groups, bound)
            cnf = cls.leq(
                lits=lits,
                weights=weights,
                groups=normalized_groups,
                bound=int(bound),
                top_id=top_id,
                encoding=enc,
                emit_amo=False,
            )

        extra = CNFPlus()
        extra.nv = int(cnf.nv)
        for group in normalized_amo + normalized_eo:
            uniq = sorted({int(lit) for lit in group})
            if len(uniq) > 1:
                for i in range(len(uniq)):
                    for j in range(i + 1, len(uniq)):
                        extra.clauses.append([-uniq[i], -uniq[j]])
        for group in normalized_eo:
            uniq = sorted({int(lit) for lit in group})
            if uniq:
                extra.clauses.append(list(uniq))
        cnf.clauses.extend(extra.clauses)
        cnf.nv = max(int(cnf.nv), int(extra.nv), top_id)
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
        if len(lits) != len(weights):
            raise ValueError("Same number of literals and weights is expected.")
        lits = [int(lit) for lit in lits]
        weights = [int(weight) for weight in weights]
        groups_were_explicit = groups is not None
        normalized_groups = _normalize_groups(groups) if groups is not None else None
        normalized_amo = _normalize_candidate_groups(amo_groups)
        normalized_eo = _normalize_candidate_groups(eo_groups)

        if normalized_groups is not None and (normalized_amo or normalized_eo):
            raise ValueError("Provide either disjoint groups or overlapping AMO/EO candidates, not both.")

        if normalized_groups is None:
            if normalized_amo or normalized_eo:
                normalized_groups = choose_overlap_partition(
                    lits,
                    weights,
                    amo_groups=normalized_amo,
                    eo_groups=normalized_eo,
                    policy=overlap_policy,
                )
            else:
                normalized_groups = [[lit] for lit in lits]

        if top_id is None:
            top_id = max((abs(int(lit)) for lit in lits), default=0)
        top_id = int(top_id)

        total_weight = int(sum(weights))
        if int(bound) < 0 or int(bound) > total_weight:
            cnf = CNFPlus()
            cnf.nv = top_id
            cnf.clauses = [[]]
            return cnf

        # No structural signal: keep the stronger dedicated equals backend.
        has_structure = any(len(group) > 1 for group in normalized_groups)
        if not has_structure and not normalized_amo and not normalized_eo:
            if all(int(weight) == 1 for weight in weights):
                from hermax.encoder.card import EncType as CardEncType
                return CardEnc.equals(lits=lits, bound=int(bound), top_id=top_id, encoding=CardEncType.kmtotalizer)
            else:
                from hermax.encoder.pb_enc import EncType as PBEncType
                from hermax.encoder.pb_enc import PBEnc

                return PBEnc.equals(
                    lits=lits,
                    weights=weights,
                    bound=int(bound),
                    top_id=top_id,
                    encoding=PBEncType.best,
                )

        upper_kwargs = {}
        if groups_were_explicit:
            upper_kwargs["groups"] = normalized_groups
        else:
            upper_kwargs["amo_groups"] = normalized_amo
            upper_kwargs["eo_groups"] = normalized_eo

        # IMPORTANT: candidate AMO/EO groups are safe for the direct (<= bound)
        # side. They are not generally safe to negate and reuse for the dual
        # side (sum(-lits) <= total-bound), especially EO groups.
        lower_kwargs = {}

        upper = cls.auto_leq(
            lits=lits,
            weights=weights,
            bound=int(bound),
            top_id=top_id,
            overlap_policy=overlap_policy,
            structured_encoding=structured_encoding,
            **upper_kwargs,
        )
        lower = cls.auto_leq(
            lits=[-int(lit) for lit in lits],
            weights=weights,
            bound=int(total_weight - int(bound)),
            top_id=max(top_id, int(upper.nv)),
            overlap_policy=overlap_policy,
            structured_encoding=structured_encoding,
            **lower_kwargs,
        )
        cnf = CNFPlus()
        cnf.clauses = [*upper.clauses, *lower.clauses]
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
        normalized_groups = _normalize_groups(groups) if groups is not None else None
        normalized_amo = _normalize_candidate_groups(amo_groups)
        normalized_eo = _normalize_candidate_groups(eo_groups)

        if normalized_groups is not None and (normalized_amo or normalized_eo):
            raise ValueError("Provide either disjoint groups or overlapping AMO/EO candidates, not both.")

        if normalized_groups is None:
            if normalized_amo or normalized_eo:
                normalized_groups = choose_overlap_partition(
                    lits,
                    [1] * len(lits),
                    amo_groups=normalized_amo,
                    eo_groups=normalized_eo,
                    policy=overlap_policy,
                )
            else:
                normalized_groups = [[lit] for lit in lits]

        if top_id is None:
            top_id = max((abs(int(lit)) for lit in lits), default=0)
        top_id = int(top_id)

        portfolio = choose_cardinality_portfolio(lits, normalized_groups, bound)
        if portfolio == "card":
            cnf = CardEnc.atmost(lits=lits, bound=int(bound), top_id=top_id, encoding=flat_encoding)
        else:
            enc = structured_encoding
            if enc == EncType.best:
                enc = choose_encoding(lits, [1] * len(lits), normalized_groups, bound)
            cnf = cls.leq(
                lits=lits,
                weights=[1] * len(lits),
                groups=normalized_groups,
                bound=int(bound),
                top_id=top_id,
                encoding=enc,
                emit_amo=False,
            )

        extra = CNFPlus()
        extra.nv = int(cnf.nv)
        for group in normalized_amo + normalized_eo:
            uniq = sorted({int(lit) for lit in group})
            if len(uniq) > 1:
                for i in range(len(uniq)):
                    for j in range(i + 1, len(uniq)):
                        extra.clauses.append([-uniq[i], -uniq[j]])
        for group in normalized_eo:
            uniq = sorted({int(lit) for lit in group})
            if uniq:
                extra.clauses.append(list(uniq))
        cnf.clauses.extend(extra.clauses)
        cnf.nv = max(int(cnf.nv), int(extra.nv), top_id)
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
