from hermax.model import Model


m = Model()

facilities = ["north", "south"]
clients = ["A", "B", "C"]

open_facility = m.bool_dict("open", facilities)
assign = m.enum_dict("assign", clients, choices=facilities, nullable=False)

for client in clients:
    for facility in facilities:
        m &= (~(assign[client] == facility) | open_facility[facility])

for facility, cap in {"north": 3, "south": 3}.items():
    m &= sum(assign[c] == facility for c in clients) <= cap

fixed_cost = {"north": 4, "south": 6}
ship_cost = {
    ("A", "north"): 1,
    ("A", "south"): 4,
    ("B", "north"): 3,
    ("B", "south"): 1,
    ("C", "north"): 2,
    ("C", "south"): 2,
}

for facility in facilities:
    m.obj[fixed_cost[facility]] += ~open_facility[facility]

for client in clients:
    for facility in facilities:
        m.obj[ship_cost[(client, facility)]] += ~(assign[client] == facility)

r = m.solve()
assert r.ok

print("status:", r.status)
print("cost:", r.cost)
print("open:", r[open_facility])
print("assign:", r[assign])
