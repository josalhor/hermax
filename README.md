# Hermax: MaxSAT Optimization for Python

<p align="center">
  <a href="https://pypi.org/project/hermax/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/hermax.svg"></a>
  <a href="https://pypi.org/project/hermax/"><img alt="PyPI wheel" src="https://img.shields.io/pypi/wheel/hermax.svg"></a>
  <a href="https://pypi.org/project/hermax/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/hermax.svg"></a>
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/License-Apache%202.0-blue.svg"></a>
  <a href="https://hermax.readthedocs.io/en/latest/"><img alt="Documentation Status" src="https://img.shields.io/readthedocs/hermax?version=latest"></a>
  <br>
  <a href="https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2026.41"><img alt="Paper: SAT 2026" src="https://img.shields.io/badge/Paper-SAT%202026-007C7A"></a>
  <img alt="Windows x86 supported" src="https://img.shields.io/badge/Windows-x86%20supported-0078D6?logo=windows">
  <img alt="Linux x86 and ARM supported" src="https://img.shields.io/badge/Linux-x86%20%26%20ARM%20supported-FCC624?logo=linux&amp;logoColor=black">
  <img alt="macOS x86 and ARM supported" src="https://img.shields.io/badge/macOS-x86%20%26%20ARM%20supported-000000?logo=apple">
</p>

![Hermax Banner](https://raw.githubusercontent.com/josalhor/hermax/main/images/banner.png)

Hermax is a Python bridge to high-performance MaxSAT backends, with a unified
IPAMIR-inspired interface for hard clauses, soft literals, assumptions, and
iterative optimization workflows.

## Why Hermax

- High-level modeling API (`hermax.model`) with typed variables, vectors, matrices, intervals, and lazy arithmetic.
- Unified API across heterogeneous MaxSAT engines.
- Incremental and non-incremental solver families
- Scientific and reproducible workflow
- Native compatibility with [PySAT](https://pysathq.github.io/)

Who Is This For?
----------------

Hermax is for combinatorially hard problems where:

* finding even a good base solution is already difficult
* the search state is mostly boolean

This is usually a better fit than MILP tooling when your problem is not mainly
about floating-point structure, large integer arithmetic, or strong LP
relaxations. In those cases, a MILP such as [PuLP](https://pypi.org/project/PuLP/),
[SCIP](https://www.scipopt.org/), or [Gurobi](https://www.gurobi.com/) is
often the more natural first choice.

If your problem is highly combinatorial but can benefit from a broader
black-box CP approach, [CP-SAT](https://developers.google.com/optimization/cp/cp_solver)
may also be a good alternative.

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
- User and API docs: https://hermax.readthedocs.io


## Modeling Example

```python
from hermax.model import Model

m = Model()

# Decision variables
x = m.int_vector("x", length=4, lb=0, ub=6)       # integer domain [0, 6]
use_bonus = m.bool("use_bonus")

# Hard constraints
m &= x.all_different()
m &= (x[0] + x[1] <= x[2] + 2)
m &= (x[3] >= 2).only_if(use_bonus)

# Prefer x[0] == 1, and charge 3 for using the bonus.
m.obj += 5 * (x[0] != 1)
m.obj += 3 * use_bonus

r = m.solve()  # auto-routes SAT/MaxSAT based on model content
print(r.status, r.cost)
```

## Incremental MaxSAT Example

CoreTrail is Hermax’s native incremental core-guided MaxSAT solver.

```python
from hermax.incremental import CoreTrail

solver = CoreTrail()
solver.add_clause([1, 2])   # hard
solver.set_soft(-1, 10)     # soft weight
solver.set_soft(-1, 6)      # update weight (last-wins)

ok = solver.solve(assumptions=[-2])
print("status:", solver.get_status().name)
if ok:
    print("cost:", solver.get_cost())
    print("model:", solver.get_model())
```

## Citation

If you use Hermax in research, please cite:

```bibtex
@InProceedings{salviahornos_et_al:LIPIcs.SAT.2026.41,
  author = {Salvia Hornos, Josep Maria and Fern\'{a}ndez Cam\'{o}n, C\`{e}sar and Mateu Pi\~{n}ol, Carles},
  title = {{Hermax: A Unified MaxSAT Library}},
  booktitle = {29th International Conference on Theory and Applications of Satisfiability Testing (SAT 2026)},
  pages = {41:1--41:13},
  series = {Leibniz International Proceedings in Informatics (LIPIcs)},
  ISBN = {978-3-95977-431-4},
  ISSN = {1868-8969},
  year = {2026},
  volume = {377},
  editor = {Ignatiev, Alexey and Szeider, Stefan},
  publisher = {Schloss Dagstuhl -- Leibniz-Zentrum f\"{u}r Informatik},
  address = {Dagstuhl, Germany},
  URL = {https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2026.41},
  URN = {urn:nbn:de:0030-drops-263478},
  doi = {10.4230/LIPIcs.SAT.2026.41},
  annote = {Keywords: MaxSAT, Incremental Solving, IPAMIR, Python, Constraint modelling}
}
```

If you use CoreTrail, please also cite its solver description:

```bibtex
@article{hornos2026coretrail,
  title={CoreTrail and ShareTrail: Incremental Core-Guided MaxSAT Solvers},
  author={Hornos, Josep Maria Salvia and Ignatiev, Alexey and Marques-Silva, Joao},
  journal={MaxSAT Evaluation 2026: Solver and Benchmark Descriptions},
  pages={17},
  year={2026},
  url={https://hdl.handle.net/10138/640150}
}
```

Please also cite the backend solver papers relevant to your experiments; see
the [documentation acknowledgments](https://hermax.readthedocs.io/en/latest/acknowledgments.html),
`CITATION.cff`, and `NOTICE` for the relevant references.

## License

This repository is licensed under Apache License 2.0. See `LICENSE`.
Third-party integrated solvers may have additional license terms.
