from hermax.encoder import PBCompiler, PBItem


items = [
    PBItem(lits=[1, 2, 3], bound=1),
    PBItem(lits=[4, 5, 6], weights=[2, 3, 5], bound=5),
    PBItem(lits=list(range(7, 19)), weights=[2] * 12, bound=5),
]
cnfs = PBCompiler.compile_batch(
    items=items,
    amo_groups=[[1, 2], [7, 8, 9], [10, 11, 12], [13, 14, 15], [16, 17, 18]],
    eo_groups=[],
    top_id=18,
)

print(f"constraints: {len(cnfs)}")
print(f"variables: {max(cnf.nv for cnf in cnfs)}")
print(f"clauses: {sum(len(cnf.clauses) for cnf in cnfs)}")
