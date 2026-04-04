from hermax.model import Model


m = Model()
m.set_objective_precision(decimals=2)

projects = ["Alpha", "Beta", "Gamma", "Delta"]
fund = m.bool_dict("fund", projects)

dev_months = {"Alpha": 5, "Beta": 8, "Gamma": 6, "Delta": 7}
m &= sum(dev_months[p] * fund[p] for p in projects) <= 18

expected_roi_millions = {"Alpha": 1.25, "Beta": 3.40, "Gamma": 2.10, "Delta": 2.80}

for p in projects:
    m.obj[expected_roi_millions[p]] += fund[p]

r = m.solve()
assert r.ok

selected = [p for p in projects if r[fund[p]]]
used_months = sum(dev_months[p] for p in selected)
total_roi = sum(expected_roi_millions.values())
selected_roi = round(total_roi - float(r.cost), 2)

print("status:", r.status)
print("total_dev_months:", used_months)
print("missed_roi_usd_millions:", r.cost)
print("selected_roi_usd_millions:", selected_roi)
print("funded_projects:", selected)
