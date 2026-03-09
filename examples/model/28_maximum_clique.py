from hermax.model import Model


vertices = [0, 1, 2, 3, 4, 5]
edges = {
    (0, 1),
    (0, 2),
    (0, 3),
    (1, 2),
    (1, 3),
    (2, 3),
    (3, 4),
    (3, 5),
    (4, 5),
}

edge_set = {tuple(sorted(e)) for e in edges}

m = Model()
pick = m.bool_dict("pick", vertices)

for i in range(len(vertices)):
    for j in range(i + 1, len(vertices)):
        u = vertices[i]
        v = vertices[j]
        if (u, v) not in edge_set:
            m &= (~pick[u] | ~pick[v])

for v in vertices:
    m.obj[1] += pick[v]

r = m.solve()

clique = [v for v in vertices if r[pick[v]]]
print("status:", r.status)
print("size:", len(clique))
print("clique:", clique)
