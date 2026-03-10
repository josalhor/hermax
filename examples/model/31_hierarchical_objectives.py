from hermax.model import Model


m = Model()
clients = ["VIP_1", "VIP_2", "Standard_1"]
drivers = ["Alice", "Bob"]
vips = ["VIP_1", "VIP_2"]

assign = m.enum_dict("assign", clients, choices=drivers, nullable=True)

for d in drivers:
    m &= sum(assign[c] == d for c in clients) <= 1

vip_served = sum(assign[v] == d for v in vips for d in drivers)
unassigned_vips = len(vips) - vip_served

travel_cost = {"Alice": 50, "Bob": 10}
travel = sum(travel_cost[d] * (assign[c] == d) for c in clients for d in drivers)

m.tier_obj.set_lexicographic(unassigned_vips, travel)

r = m.solve(lex_strategy="incremental")
assert r.ok

print("status:", r.status)
print("unassigned_vips (tier 0):", r.tier_costs[0])
print("travel_cost      (tier 1):", r.tier_costs[1])
print("assignments:", r[assign])
