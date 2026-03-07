from pysat.formula import IDPool, WCNF

from hermax.non_incremental import CGSSSolver
from hermax.non_incremental.incomplete import Loandra
from hermax.portfolio import PortfolioSolver


wcnf = WCNF()
vpool = IDPool(start_from=1)
a = vpool.id("A")
b = vpool.id("B")
wcnf.append([a, b])          # A OR B: at least one variable must be true
wcnf.append([-a, -b])        # (NOT A) OR (NOT B): A and B cannot both be true
wcnf.append([-a], weight=5)  # soft literal -A: pay 5 if A=True
wcnf.append([-b], weight=2)  # soft literal -B: pay 2 if B=True

portfolio = PortfolioSolver(
    [CGSSSolver, Loandra],
    formula=wcnf,
    per_solver_timeout_s=3.0,
    overall_timeout_s=5.0,
    max_workers=2,
    selection_policy="first_optimal_or_best_until_timeout",
)

ok = portfolio.solve()
print("feasible:", ok)
print("status:", portfolio.get_status().name)
if ok:
    print("cost:", portfolio.get_cost())
    print("model:", portfolio.get_model())
