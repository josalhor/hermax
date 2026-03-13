from hermax.internal.structuredpb import OverlapPolicy, StructuredPBEnc


def main() -> None:
    lits = [1, 2, 3, 4, 5]
    weights = [6, 4, 7, 5, 3]
    bound = 10
    amo_groups = [[1, 2, 3], [2, 3, 4]]
    eo_groups = [[4, 5]]

    cnf = StructuredPBEnc.auto_leq(
        lits=lits,
        weights=weights,
        bound=bound,
        amo_groups=amo_groups,
        eo_groups=eo_groups,
        overlap_policy=OverlapPolicy.paper_best_fit_dynamic_future,
    )

    print("overlap_policy=paper_best_fit_dynamic_future")
    print(f"nv={cnf.nv}")
    print(f"clauses={len(cnf.clauses)}")
    print("first_clauses=")
    for clause in cnf.clauses[:8]:
        print(clause)


if __name__ == "__main__":
    main()
