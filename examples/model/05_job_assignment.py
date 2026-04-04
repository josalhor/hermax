from hermax.model import Model


m = Model()

workers = ["alice", "bob", "carol"]
tasks = ["t1", "t2", "t3"]
cost = {
    ("t1", "alice"): 5,
    ("t1", "bob"): 1,
    ("t1", "carol"): 3,
    ("t2", "alice"): 2,
    ("t2", "bob"): 6,
    ("t2", "carol"): 1,
    ("t3", "alice"): 4,
    ("t3", "bob"): 3,
    ("t3", "carol"): 2,
}

assign = m.enum_dict("assign", tasks, choices=workers, nullable=False)

for w in workers:
    chosen_by_worker = [(assign[t] == w) for t in tasks]
    m &= m.vector(chosen_by_worker, name=f"worker_{w}_tasks").at_most_one()

for t in tasks:
    for w in workers:
        m.obj[cost[(t, w)]] += ~(assign[t] == w)

r = m.solve()

print("status:", r.status)
print("cost:", r.cost)
print("assignment:", {t: r[assign[t]] for t in tasks})
