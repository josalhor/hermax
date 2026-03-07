from hermax.model import Model

m = Model()

end_times = m.int_vector("end", length=6, lb=0, ub=24)

# Keep the demo small and deterministic.
for i, v in enumerate([2, 5, 11, 13, 17, 20]):
    m &= (end_times[i] == v)

morning = [t.in_range(0, 11) for t in end_times]
afternoon = [t.in_range(12, 17) for t in end_times]
evening = [t.in_range(18, 23) for t in end_times]

# Histogram-style counting over reusable bin indicators.
m &= (sum(morning) == 3)
m &= (sum(afternoon) == 2)
m &= (sum(evening) == 1)

r = m.solve()
assert r.ok

print("end_times =", r[end_times])
print("morning_count =", sum(1 for b in r[morning] if b))
print("afternoon_count =", sum(1 for b in r[afternoon] if b))
print("evening_count =", sum(1 for b in r[evening] if b))
