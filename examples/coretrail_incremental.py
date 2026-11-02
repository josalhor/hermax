"""Reuse CoreTrail across related incremental MaxSAT queries."""
from hermax.incremental import CoreTrail

solver = CoreTrail()

solver.add_clause([1, 2])
solver.set_soft(-1, 6)
solver.set_soft(-2, 3)

for assumptions in ([], [-2]):
    if solver.solve(assumptions=assumptions):
        print(f"assumptions={assumptions}: cost={solver.get_cost()}")

solver.set_soft(-1, 2)
if solver.solve():
    print(f"after weight update: cost={solver.get_cost()}")
