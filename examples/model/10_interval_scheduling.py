from hermax.model import Model


m = Model()

task_a = m.interval("A", start=0, duration=5, end=24)
task_b = m.interval("B", start=0, duration=3, end=24)
task_c = m.interval("C", start=0, duration=4, end=24)

m &= task_a.no_overlap(task_b)
m &= task_b.no_overlap(task_c)
m &= task_a.no_overlap(task_c)
m &= task_a.ends_before(task_c)

m.obj[1] += task_c.start

r = m.solve()

print("status:", r.status)
print("cost:", r.cost)
print("A:", r[task_a])
print("B:", r[task_b])
print("C:", r[task_c])
