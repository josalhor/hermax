from pathlib import Path

from hermax.formula import load_formula
from hermax.incremental import CoreTrail

# Existing PySAT WCNF objects can also be supplied directly to Hermax solvers.
wcnf = load_formula(Path(__file__).parent / "data" / "load_formula.wcnf")

solver = CoreTrail(formula=wcnf)
ok = solver.solve()
print("feasible:", ok)
if ok:
    print("status:", solver.get_status().name)
    print("cost:", solver.get_cost())
    print("model:", solver.get_model())
