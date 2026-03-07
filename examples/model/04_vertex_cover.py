from hermax.model import Model


m = Model()

vertices = [0, 1, 2, 3, 4]
edges = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)]
cost = {0: 2, 1: 1, 2: 2, 3: 1, 4: 2}

cover = m.bool_dict("cover", vertices)

for u, v in edges:
    m &= (cover[u] | cover[v])  # each edge must have at least one endpoint in the cover

for v in vertices:
    m.obj[cost[v]] += ~cover[v]  # [~cover[v]] is violated when cover[v] is true -> pay cost if selected

r = m.solve()

chosen = [v for v in vertices if r[cover[v]]]
print("status:", r.status)
print("cost:", r.cost)
print("vertex_cover:", chosen)
