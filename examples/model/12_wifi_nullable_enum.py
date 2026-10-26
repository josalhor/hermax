from hermax.model import Model


m = Model()

routers = [0, 1, 2, 3]
edges = [(0, 1), (1, 2), (2, 3), (0, 3)]
freqs = ["f1", "f2", "f3"]

state = m.enum_dict("router_state", routers, choices=freqs, nullable=True)

for u, v in edges:
    for f in freqs:
        m &= (~(state[u] == f) | ~(state[v] == f))

for r in routers:
    online = m.bool()
    m &= state[r].is_in(freqs).iff(online)
    m.obj += 5 * ~online
    m.obj += state[r] == "f1"
    m.obj += 2 * (state[r] == "f2")
    m.obj += state[r] == "f3"

r = m.solve()

print("status:", r.status)
print("cost:", r.cost)
print("router_state:", r[state])
