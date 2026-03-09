from hermax.model import Model
from hermax.portfolio import CompletePortfolioSolver


m = Model()

a = m.bool("a")
b = m.bool("b")

m &= (a | b)

# Prefer a=False and b=True.
m.obj[3] += ~a
m.obj[1] += ~b

r = m.solve(
    solver=CompletePortfolioSolver,
    solver_kwargs={
        "max_workers": 1,
        "overall_timeout_s": 3.0,
        "per_solver_timeout_s": 2.0,
    },
)
assert r.ok

print("status:", r.status)
print("cost:", r.cost)
print("a:", r[a])
print("b:", r[b])
