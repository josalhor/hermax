from typing import List, Dict, Any, Optional, Set, Tuple
from hermax.encoder.pbamo import PBAMOEnc
from hermax.internal.kmerge import (
    DEFAULT_KMERGE_CONFIG,
    KMergeConfig,
    PBConstraintStub,
    partition_constraints,
    resolve_cluster_config,
)
from dataclasses import dataclass

@dataclass(frozen=True)
class PBItem:
    """
    Represents a single Pseudo-Boolean or Cardinality constraint for compilation.

    :param lits: DIMACS-style literals.
    :param bound: The Right-Hand Side (RHS) value.
    :param weights: Non-negative integer weights. If None, all weights are assumed to be 1.
    :param cmp_op: Comparison operator (``'<='`` or ``'=='``).
    """
    lits: List[int]
    bound: int
    weights: Optional[List[int]] = None
    cmp_op: str = "<="

    @property
    def is_cardinality(self) -> bool:
        """Returns True if all weights are 1 (or implicit)."""
        return self.weights is None or all(w == 1 for w in self.weights)

    def get_weights(self) -> List[int]:
        """Returns the actual weights list, materializing unit weights if necessary."""
        if self.weights is not None:
            return self.weights
        return [1] * len(self.lits)


class PBCompiler:
    """
    The central entry point for compiling batches of Pseudo-Boolean (PB) constraints.

    PBCompiler ensures that the SAT encoding is as compact and
    efficient as possible.
    """

    @classmethod
    def compile_batch(cls, items: List[PBItem], amo_groups: List[List[int]], eo_groups: List[List[int]], top_id: int):
        """
        Compiles a batch of PB constraints into SAT.

        This method performs a multi-stage compilation process:

        1. **Clustering**: Analysis of variable connectivity to find related constraint sets.
        2. **K-Merge Extraction**: Solving for optimal shared bases within clusters.
        3. **Priority Encoding**: Sorting remaining constraints to maximize structural learning.
        4. **In-Batch Learning**: Updating the structural knowledge base in real-time.

        :param items: A list of :class:`PBItem` objects to be compiled.
        :param amo_groups: Known At-Most-One literal groups.
        :param eo_groups: Known Exactly-One literal groups.
        :param top_id: The current maximum variable ID in the solver.
        :return: A list of CNFPlus objects containing the generated SAT clauses and auxiliary variables.
        """
        return cls.compile_batch_with_options(
            items=items,
            amo_groups=amo_groups,
            eo_groups=eo_groups,
            top_id=top_id,
            merge_pb_optimization=True,
            kmerge_config=DEFAULT_KMERGE_CONFIG,
        )

    @classmethod
    def compile_batch_with_options(
        cls,
        items: List[PBItem],
        amo_groups: List[List[int]],
        eo_groups: List[List[int]],
        top_id: int,
        *,
        merge_pb_optimization: bool,
        kmerge_config: KMergeConfig | None = None,
    ):
        results = []
        kmerge_indices = set()
        current_top = int(top_id)
        effective_kmerge_config = kmerge_config or DEFAULT_KMERGE_CONFIG

        # 1. K-MERGE Optimization
        # Group by connected components (shared variables)
        merge_candidates = [
            idx
            for idx, item in enumerate(items)
            if not item.is_cardinality and str(item.cmp_op) == "<=" and len(item.lits) > 2
        ]
        if bool(merge_pb_optimization) and len(merge_candidates) >= 2:
            adj = [[] for _ in range(len(items))]
            for pos_i, i in enumerate(merge_candidates):
                for j in merge_candidates[pos_i + 1 :]:
                    # Check for overlap
                    if set(items[i].lits) & set(items[j].lits):
                        adj[i].append(j)
                        adj[j].append(i)
            
            visited = [False] * len(items)
            for i in merge_candidates:
                if not visited[i] and adj[i]:
                    comp = []
                    q = [i]
                    visited[i] = True
                    while q:
                        u = q.pop(0)
                        comp.append(u)
                        for v in adj[u]:
                            if not visited[v]:
                                visited[v] = True
                                q.append(v)
                    
                    if len(comp) >= 2:
                        comp_items = [items[idx] for idx in comp]
                        mean_term_len = (
                            sum(len(item.lits) for item in comp_items) / float(len(comp_items))
                            if comp_items
                            else 0.0
                        )
                        if mean_term_len < float(getattr(effective_kmerge_config, "min_mean_term_len_for_merge", 0.0)):
                            continue
                        union_set = sorted(set().union(*(c.lits for c in comp_items)))
                        core = tuple(union_set)
                        
                        stubs = []
                        for c in comp_items:
                            lit_to_w = {lit: w for lit, w in zip(c.lits, c.get_weights())}
                            ordered_w = tuple(lit_to_w.get(l, 0) for l in core)
                            stubs.append(PBConstraintStub(lits=core, weights=ordered_w, 
                                                        bound=c.bound, op=c.cmp_op))
                        
                        component_config = resolve_cluster_config(stubs, effective_kmerge_config)
                        partitions = partition_constraints(stubs, config=component_config)
                        for part in partitions:
                            if len(part) < 2:
                                continue
                            
                            for p_idx in part:
                                kmerge_indices.add(comp[p_idx])
                            
                            cluster_stubs = [stubs[p_idx] for p_idx in part]
                            cluster_config = resolve_cluster_config(cluster_stubs, effective_kmerge_config)
                            cluster_cnf = PBAMOEnc.multi_leq(
                                lits=core,
                                stubs=cluster_stubs,
                                top_id=current_top,
                                kmerge_config=cluster_config,
                            )
                            results.append(cluster_cnf)
                            current_top = max(current_top, cluster_cnf.nv)

        # 2. Sorting for remaining constraints
        remaining = [(idx, item) for idx, item in enumerate(items) if idx not in kmerge_indices]
        
        local_amo = list(amo_groups)
        local_eo = list(eo_groups)

        def _priority(item):
            cmp_op = str(item.cmp_op)
            bound = int(item.bound)
            is_card = item.is_cardinality
            is_amo_eo = is_card and bound == 1 and cmp_op in {"<=", "=="}
            if is_amo_eo: return 0
            if is_card: return 1
            return 2

        sorted_remaining = sorted(remaining, key=lambda x: (_priority(x[1]), x[0]))

        # 3. Compilation
        # Helper to find overlaps with local structure
        def _get_overlaps(pb_lits, cur_amo, cur_eo):
            pb_lit_set = set(pb_lits)
            pb_amo = []
            pb_eo = []
            for group in cur_amo:
                overlap = [lit for lit in group if lit in pb_lit_set]
                if len(overlap) > 1:
                    pb_amo.append(overlap)
            for group in cur_eo:
                overlap = [lit for lit in group if lit in pb_lit_set]
                if len(overlap) == len(group) and len(overlap) > 1:
                    pb_eo.append(overlap)
                elif len(overlap) > 1:
                    pb_amo.append(overlap)
            return pb_amo, pb_eo

        for idx, item in sorted_remaining:
            lits = item.lits
            weights = item.get_weights()
            bound = item.bound
            cmp_op = item.cmp_op
            
            pb_amo, pb_eo = _get_overlaps(lits, local_amo, local_eo)
            
            if cmp_op == "<=":
                cnf = PBAMOEnc.auto_leq(
                    lits=lits,
                    weights=weights,
                    bound=bound,
                    amo_groups=pb_amo,
                    eo_groups=pb_eo,
                    top_id=current_top
                )
            else: # "=="
                cnf = PBAMOEnc.auto_eq(
                    lits=lits,
                    weights=weights,
                    bound=bound,
                    amo_groups=pb_amo,
                    eo_groups=pb_eo,
                    top_id=current_top
                )
            
            results.append(cnf)
            current_top = max(current_top, cnf.nv)
            
            # EAGER LEARNING: Register if this was an AMO/EO
            if item.is_cardinality and item.bound == 1:
                if item.cmp_op == "<=":
                    local_amo.append(item.lits)
                elif item.cmp_op == "==":
                    local_eo.append(item.lits)
            
        return results
