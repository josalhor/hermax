from hermax.model import Model


m = Model()

tasks = ["api", "ui", "ops"]
workers = ["alice", "bob"]

assign = m.enum_dict("assign", tasks, choices=workers, nullable=True)

for worker, cap in {"alice": 1, "bob": 1}.items():
    m &= sum(assign[t] == worker for t in tasks) <= cap

m &= ~(assign["ops"] == "bob")

unassigned_penalty = {"api": 8, "ui": 6, "ops": 2}
for task in tasks:
    m.obj[unassigned_penalty[task]] += assign[task].is_in(workers)

for task, worker, cost in [
    ("api", "alice", 1),
    ("api", "bob", 2),
    ("ui", "alice", 3),
    ("ui", "bob", 1),
    ("ops", "alice", 4),
]:
    m.obj[cost] += ~(assign[task] == worker)

r = m.solve()
assert r.ok

print("status:", r.status)
print("cost:", r.cost)
print("assign:", r[assign])
