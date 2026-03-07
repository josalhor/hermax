# Hermax: Incremental MaxSAT Solvers for Python

[![Documentation Status](https://readthedocs.org/projects/hermax/badge/?version=latest)](https://hermax.readthedocs.io/en/latest/?badge=latest)

![Hermax Banner](https://raw.githubusercontent.com/josalhor/hermax/main/images/banner.png)

Hermax is a Python bridge to high-performance MaxSAT backends, with a unified
IPAMIR-inspired interface for hard clauses, soft literals, assumptions, and
iterative optimization workflows.

## Why Hermax

- High-level modeling API (`hermax.model`) with typed variables, vectors, matrices, intervals, and lazy arithmetic.
- Unified API across heterogeneous MaxSAT engines.
- Incremental and non-incremental solver families under the same contract.
- Scientific and reproducible workflow orientation (papers, references, benchmark-ready APIs).
- Native compatibility with PySAT `WCNF` / `WCNFPlus`.

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

## Scientific Context

Hermax is designed for the incremental MaxSAT setting formalized by:

- Niskanen, Berg, Jarvisalo. *Incremental Maximum Satisfiability*. SAT 2022.

Solver families available in Hermax are linked to established research lines:

- RC2: Ignatiev, Morgado, Marques-Silva. *RC2: An Efficient MaxSAT Solver*. JSAT 2019.
- UWrMaxSAT: Piotrow. *UWrMaxSat: Efficient Solver for MaxSAT and Pseudo-Boolean Problems*. ICTAI 2020.
- EvalMaxSAT: Avellaneda. *EvalMaxSAT*. MaxSAT Evaluation (solver descriptions), 2023.
- MaxHS: Bacchus. *MaxHS in the 2020 MaxSAT Evaluation*, 2020.
- iMaxHS: Niskanen, Berg, Jarvisalo. *Enabling Incrementality in the Implicit Hitting Set Approach to MaxSAT Under Changing Weights*. CP 2021.
- CASHWMaxSAT line: Pan, Wang, Cai. *An Efficient Core-Guided Solver for Weighted Partial MaxSAT*. IJCAI 2025.


## Documentation

- User and API docs: https://hermax.readthedocs.io

## Citation

If you use Hermax in research:

1. Cite the repository: https://github.com/josalhor/hermax
2. Cite the backend solver papers relevant to your experiments.
3. See machine-readable metadata in `CITATION.cff`.
4. See additional attribution and latest-paper list in `NOTICE`.

## License

This repository is licensed under Apache License 2.0. See `LICENSE`.
Third-party integrated solvers may have additional license terms.
