from hermax.model import Model

m = Model()

timeline = m.int_vector("lvl", length=6, lb=0, ub=10)
for i, v in enumerate([1, 4, 2, 7, 6, 8]):
    m &= (timeline[i] == v)

watermark = timeline.running_max(name="watermark")

# Check the running-maximum semantics at one position.
m &= (watermark[3] == 7)

r = m.solve()
assert r.ok

print("timeline   =", r[timeline])
print("watermark  =", r[watermark])

