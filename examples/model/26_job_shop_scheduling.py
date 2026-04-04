from hermax.model import Model


jobs = {
    "J1": [("M1", 3), ("M2", 2), ("M3", 2)],
    "J2": [("M2", 2), ("M3", 1), ("M1", 4)],
    "J3": [("M3", 4), ("M1", 3), ("M2", 1)],
}

horizon = sum(duration for ops in jobs.values() for _, duration in ops)

m = Model()
ops = {}
machine_ops = {"M1": [], "M2": [], "M3": []}

for job, route in jobs.items():
    for step, (machine, duration) in enumerate(route):
        task = m.interval(f"{job}_{step}", start=0, duration=duration, end=horizon)
        ops[(job, step)] = task
        machine_ops[machine].append(task)

for job, route in jobs.items():
    for step in range(len(route) - 1):
        m &= ops[(job, step)].ends_before(ops[(job, step + 1)])

for machine, tasks in machine_ops.items():
    for i in range(len(tasks)):
        for j in range(i + 1, len(tasks)):
            m &= tasks[i].no_overlap(tasks[j])

makespan = m.upper_bound(
    [ops[(job, len(route) - 1)].end for job, route in jobs.items()],
    name="makespan",
)

m.obj[1] += makespan

r = m.solve()

print("status:", r.status)
print("makespan:", r[makespan])
for job, route in jobs.items():
    print(job + ":")
    for step, (machine, duration) in enumerate(route):
        task = ops[(job, step)]
        slot = r[task]
        print(
            f"  op{step + 1}: {machine} dur={duration} "
            f"start={slot['start']} end={slot['end']}"
        )
