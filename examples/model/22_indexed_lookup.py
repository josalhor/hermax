from hermax.model import Model


m = Model()

durations = m.int_vector("duration", length=3, lb=0, ub=10)
for i, value in enumerate([6, 3, 5]):
    m &= (durations[i] == value)

machine = m.int("machine", 0, 3)
chosen_duration = m.int("chosen_duration", 0, 10)

# Pick the duration attached to the chosen machine.
m &= (durations[machine] == chosen_duration)

m &= (machine != 0)

m.obj[1] += chosen_duration

r = m.solve()
assert r.ok

print("status:", r.status)
print("cost:", r.cost)
print("durations:", r[durations])
print("machine:", r[machine])
print("chosen_duration:", r[chosen_duration])
