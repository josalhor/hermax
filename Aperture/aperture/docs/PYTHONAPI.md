# Aperture Python API

Aperture is a SAT-based optimization solver providing a Python interface for:
- **SAT solving** – check satisfiability of CNF Boolean formulas
- **MaxSAT solving** – minimize satisfied (weighted) soft literals
- **OBV solving** – optimize modulo bit-vector problems
- **Black-box optimization** – optimize generic objective functions

All solving quiries can be called incrementally under assumptions.

## Quick Start

```python
import aperture as ap

solver = ap.Solver(sat_solver="topor")
x = solver.new_var()
y = solver.new_var()

solver.add_clause(ap.lits([x, y]))  # x OR y

sat = solver.solve()

if sat:
    print("SAT")
    print(solver.get_latest_solution())
else:
    print(solver.get_latest_solve_status())
```

## Supported SAT Solvers

- `"topor"` 
- `"cadical"`
- `"glucose"` (default)
- `"kissat"` – initial SAT query only

## Core Methods

| Method | Purpose |
|--------|---------|
| `new_var()` | Create a new Boolean variable |
| `add_clause(lits)` | Add a clause |
| `solve(assumptions=[])` | Solve SAT |
| `solve_maxsat(assumptions, soft_lits, fix_model_value, callback_on_solution_found=None)` | Solve MaxSAT |
| `solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value, callback_on_solution_found=None)` | Solve weighted MaxSAT |
| `solve_obv(assumptions, targets, callback_on_solution_found=None)` | Optimize bit-vectors |
| `solve_black_box(assumptions, observables, pb_func, callback_on_solution_found=None)` | Black-box optimization |
| `get_latest_solution()` | Get solution (assignment) of the last solve query |
| `get_latest_solve_status()` | Get status ("SAT", "UNSAT", "ERROR", "UNKNOWN") |

## Constraints

Add cardinality and pseudo-Boolean constraints:
- `add_constraint_less_than((w)lits, rhs, selector=None)`
- `add_constraint_less_than_equal((w)lits, rhs, selector=None)`
- `add_constraint_equal(lits, rhs, selector=None)`
- `add_constraint_greater_than_equal(lits, rhs, selector=None)`
- `add_constraint_greater_than(lits, rhs, selector=None)`

All methods return `bool` ans supports adding an optional selector to all the generated clauses. <br>
Note that currently only < and <= constraints are supported for weighted literals (wlits).

## Documentation

For further information and examples, see the [notebook](https://github.com/YamSln/Aperture/tree/main/aperture/docs/notebooks) in the docs/ directory. ReadTheDocs documentation will be available in the future.