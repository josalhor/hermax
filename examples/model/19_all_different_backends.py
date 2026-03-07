from hermax.model import Model

m = Model()

xs = m.int_vector("x", length=4, lb=0, ub=6)

# Two equivalent ways to model all_different on finite-domain IntVars.
pairwise = xs.all_different(backend="pairwise")
bipartite = xs.all_different(backend="bipartite")

# Use one backend in the model; leave the other as a reference object.
m &= bipartite

# Pin a few values and let the solver infer the rest.
m &= (xs[0] == 1)
m &= (xs[1] == 3)
m &= (xs[2] <= 2)

r = m.solve()
assert r.ok

print("xs =", r[xs])
print("all distinct =", len(set(r[xs])) == len(r[xs]))
print("pairwise_clause_count =", len(pairwise.clauses))
print("bipartite_clause_count =", len(bipartite.clauses))

