from hermax.incremental import UWrMaxSATCompetition as UWrMaxSAT

from wifi_lib import build_var_map, generate_congestion_weights, generate_random_network


routers, edges = generate_random_network(num_routers=8, edge_prob=0.25)
freqs = {1, 2, 3}
weights = generate_congestion_weights(routers, freqs, min_w=5, max_w=20)
var_map = build_var_map(routers, freqs, allow_offline=False)

solver = UWrMaxSAT()

for r in routers:
    solver.add_clause([var_map[(r, f)] for f in freqs])  # f1 OR f2 OR f3: router r must pick one channel
    for f1 in freqs:
        for f2 in freqs:
            if f1 < f2:
                solver.add_clause(
                    [-var_map[(r, f1)], -var_map[(r, f2)]]
                )  # (NOT rf1) OR (NOT rf2): router r cannot pick both channels

for u, v in edges:
    for f in freqs:
        solver.add_clause(
            [-var_map[(u, f)], -var_map[(v, f)]]
        )  # (NOT u@f) OR (NOT v@f): interfering routers cannot share channel f

for r in routers:
    for f in freqs:
        solver.set_soft(-var_map[(r, f)], weights[(r, f)])  # pay weight if router r uses channel f

ok = solver.solve()
print("feasible:", ok)
if ok:
    print("status:", solver.get_status().name)
    print("cost:", solver.get_cost())
    print("model_prefix:", solver.get_model()[:12])
