from pysat.formula import IDPool

from hermax.portfolio import PortfolioSolver

vpool = IDPool(start_from=1)
x1 = vpool.id("x1")
x2 = vpool.id("x2")

complete_portfolio = PortfolioSolver.complete(
    per_solver_timeout_s=2.0,
    overall_timeout_s=4.0,
    max_workers=2,
)

complete_portfolio.add_clause([x1, x2])     # x1 OR x2: at least one must be true
complete_portfolio.add_clause([-x1, -x2])   # (NOT x1) OR (NOT x2): at most one is true
complete_portfolio.add_soft_unit(-x1, 4)    # pay 4 if x1=True
complete_portfolio.add_soft_unit(-x2, 1)    # pay 1 if x2=True

ok = complete_portfolio.solve()
print("complete preset feasible:", ok)
print("complete preset status:", complete_portfolio.get_status().name)
if ok:
    print("complete preset cost:", complete_portfolio.get_cost())



performance_portfolio = PortfolioSolver.performance(
    per_solver_timeout_s=2.0,
    overall_timeout_s=4.0,
    max_workers=2,
    selection_policy="first_valid",
)

performance_portfolio.add_clause([x1])      # x1: force x1=True
performance_portfolio.add_soft_unit(-x1, 3) # pay 3 because x1 is forced true

ok2 = performance_portfolio.solve()
print("performance preset feasible:", ok2)
print("performance preset status:", performance_portfolio.get_status().name)
if ok2:
    print("performance preset cost:", performance_portfolio.get_cost())
