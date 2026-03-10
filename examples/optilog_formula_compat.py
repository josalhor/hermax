import importlib.util

from hermax.incremental import UWrMaxSAT

if importlib.util.find_spec("optilog") is None:
    raise RuntimeError(
        """OptiLog is not installed.
Install: pip install "hermax[optilog]"."""
    )

from optilog.formulas import WCNF as OptiWCNF

formula = OptiWCNF()
formula.extend_vars(2)
a = 1
b = 2
formula.add_clause([a, b])  # A OR B: at least one variable must be true
formula.add_clauses([[-a], [-b]], 1)  # soft literals: pay 1 if A=True or B=True

solver = UWrMaxSAT(formula=formula)
ok = solver.solve()
print("status:", solver.get_status().name)
if ok:
    print("cost:", solver.get_cost())
    print("model:", solver.get_model())
