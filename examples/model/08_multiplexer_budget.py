from hermax.model import Model


m = Model()

worker = m.int("worker", lb=0, ub=4)
budget = m.int("budget", lb=20, ub=121)
worker_costs = [20, 40, 75, 120]

m &= (worker_costs @ worker <= budget)  # element constraint: selected worker cost must fit budget
m &= (budget <= 80)

r = m.solve()

print("status:", r.status)
print("worker:", r[worker])
print("budget:", r[budget])
print("selected_cost:", worker_costs[r[worker]])
