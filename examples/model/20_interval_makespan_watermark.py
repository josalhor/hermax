from hermax.model import Model

m = Model()

a = m.interval("A", start=0, duration=3, end=12)
b = m.interval("B", start=0, duration=4, end=12)
c = m.interval("C", start=0, duration=2, end=12)

m &= a.no_overlap(b)
m &= b.no_overlap(c)

# Make task A happen before B as an extra precedence.
m &= a.ends_before(b)

makespan = m.max([a.end, b.end, c.end], name="makespan")

# Minimize the schedule end time directly through IntVar objective lowering.
m.obj[1] += makespan

r = m.solve()
assert r.ok

print("A =", r[a])
print("B =", r[b])
print("C =", r[c])
print("makespan =", r[makespan])

