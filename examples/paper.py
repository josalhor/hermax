from hermax.model import Model

m = Model()

# Exactly one deployment plan is active.
plan = m.bool_vector("plan", length=3)  # plan[0]=A, plan[1]=B, plan[2]=C
m &= plan.exactly_one()

# Context literals for what-if solving.
rush = m.bool("rush")
maintenance = m.bool("maintenance")

# Context-gated hard constraints.
m &= plan[2].only_if(rush)             # rush hour requires plan C
m &= (~plan[2]).only_if(maintenance)   # maintenance forbids plan C

# Incremental SAT usage via assumptions.
r1 = m.solve(assumptions=[~rush, ~maintenance])
print(r1.status, r1[plan])  # sat, one feasible plan

r2 = m.solve(assumptions=[rush, maintenance])
print(r2.status)  # unsat (C required and forbidden)

# Add soft preferences after SAT solves: model auto-upgrades to incremental MaxSAT.
prefer_a = m.add_soft(plan[0], weight=10)
prefer_b = m.add_soft(plan[1], weight=6)

r3 = m.solve(assumptions=[~rush, ~maintenance])
print(f"Before reweight: cost={r3.cost}, plan={r3[plan]}")

# Change preference strength without rebuilding model or solver.
m.update_soft_weight(prefer_a, new_weight=2)

r4 = m.solve(assumptions=[~rush, ~maintenance])
print(f"After reweight:  cost={r4.cost}, plan={r4[plan]}")
