# Hermax: Incremental MaxSAT Solvers for Python

[![PyPI version](https://img.shields.io/pypi/v/hermax.svg)](https://pypi.org/project/hermax/)
[![PyPI wheel](https://img.shields.io/pypi/wheel/hermax.svg)](https://pypi.org/project/hermax/)
[![Python versions](https://img.shields.io/pypi/pyversions/hermax.svg)](https://pypi.org/project/hermax/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Documentation Status](https://readthedocs.org/projects/hermax/badge/?version=latest)](https://hermax.readthedocs.io/en/latest/?badge=latest)

![Hermax Banner](https://raw.githubusercontent.com/josalhor/hermax/main/images/banner.png)

Hermax is a Python bridge to high-performance MaxSAT backends, with a unified
IPAMIR-inspired interface for hard clauses, soft literals, assumptions, and
iterative optimization workflows.

## Why Hermax

- High-level modeling API (`hermax.model`) with typed variables, vectors, matrices, intervals, and lazy arithmetic.
- Unified API across heterogeneous MaxSAT engines.
- Incremental and non-incremental solver families
- Scientific and reproducible workflow
- Native compatibility with PySAT

Who Is This For?
----------------

Hermax is for combinatorially hard problems where:

* finding even a good base solution is already difficult
* the search state is mostly boolean

This is usually a better fit than MILP tooling when your problem is not mainly
about floating-point structure, large integer arithmetic, or strong LP
relaxations. In those cases, a MILP such as PuLP, SCIP, or Gurobi is
often the more natural first choice.

If your problem is highly combinatorial but can benefit from a broader
black-box CP approach, CP-SAT may also be a good alternative.

Hermax is especially relevant for:

* engineers building repeated optimization workflows around hard clauses, soft
  literals, assumptions, and iterative solve loops,
* users who already work with clauses, WCNF, or incremental solver-style APIs,
  and
* researchers comparing MaxSAT backends behind a common Python interface.

## Installation

Core install:

```bash
pip install hermax
```

## Modeling Example

```python
from hermax.model import Model

m = Model()

# Decision variables
x = m.int_vector("x", length=4, lb=0, ub=6)       # integer domain [0, 5]
use_bonus = m.bool("use_bonus")

# Hard constraints
m &= x.all_different()
m &= (x[0] + x[1] <= x[2] + 2)
m &= (x[3] >= 2).only_if(use_bonus)

# Soft objective terms
m.obj[5] += (x[0] == 1)
m.obj[3] += ~use_bonus

r = m.solve()  # auto-routes SAT/MaxSAT based on model content
print(r.status, r.cost)
```

## Incremental MaxSAT Example

```python
from hermax.incremental import UWrMaxSAT

solver = UWrMaxSAT()
try:
    solver.add_clause([1, 2])   # hard
    solver.set_soft(-1, 10)     # soft weight
    solver.set_soft(-1, 6)      # update weight (last-wins)

    ok = solver.solve(assumptions=[-1])
    print("status:", solver.get_status().name)
    if ok:
        print("cost:", solver.get_cost())
        print("model:", solver.get_model())
finally:
    solver.close()
```

## Documentation

- User and API docs: https://hermax.readthedocs.io

## Citation

Hermax is designed for the incremental MaxSAT setting formalized by:

- Niskanen, Berg, Jarvisalo. *Incremental Maximum Satisfiability*. SAT 2022.

If you use Hermax in research:

1. Cite the repository: https://github.com/josalhor/hermax
2. Cite the backend solver papers relevant to your experiments.
3. See machine-readable metadata in `CITATION.cff`.
4. See additional attribution and latest-paper list in `NOTICE`.

## License

This repository is licensed under Apache License 2.0. See `LICENSE`.
Third-party integrated solvers may have additional license terms.
