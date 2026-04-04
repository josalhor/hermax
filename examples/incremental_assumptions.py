from pysat.formula import IDPool

from hermax.incremental import UWrMaxSAT


def solve_with_assumption(solver: UWrMaxSAT, assumption: int) -> None:
    ok = solver.solve(assumptions=[assumption])
    print(f"assumption [{assumption}] -> feasible={ok}")
    if ok:
        print("  cost:", solver.get_cost())
        print("  model:", solver.get_model())


solver = UWrMaxSAT()
vpool = IDPool(start_from=1)
x1 = vpool.id("x1")
x2 = vpool.id("x2")

# x1 OR x2: at least one variable must be true.
solver.add_clause([x1, x2])

# Soft literals make True assignments expensive, so the optimum prefers False.
solver.set_soft(-x1, 3)  # pay 3 if x1=True
solver.set_soft(-x2, 2)  # pay 2 if x2=True

solve_with_assumption(solver, -x1)
solve_with_assumption(solver, x2)
