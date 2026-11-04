"""Reserve input IDs and remap native encoder auxiliaries in an IDPool."""


def update_vids(cnf, top, vpool):
    """Update the pool and avoid occupied ranges when remapping auxiliaries.

    ``top`` is the maximum original variable ID used as native encoder input,
    including conditionals. Every variable above it is an auxiliary variable.
    """
    vpool.top = max(vpool.top, top)
    while vpool._occupied and vpool._occupied[0][0] <= vpool.top:
        vpool.top = max(vpool.top, vpool._occupied[0][1])
        vpool._occupied.pop(0)

    if vpool.top == top and not (vpool._occupied and vpool._occupied[0][0] <= cnf.nv):
        vpool.top = max(vpool.top, cnf.nv)
        return

    mapping = {var: vpool._next() for var in range(top + 1, cnf.nv + 1)}
    if mapping:
        # Formula clauses are immutable tuples backed by native ClauseStorage;
        # construct a new collection instead of mutating clause views.
        cnf.clauses = [
            [mapping.get(abs(lit), abs(lit)) * (1 if lit > 0 else -1) for lit in clause]
            for clause in cnf.clauses
        ]
    cnf.nv = vpool.top
