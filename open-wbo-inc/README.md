# OpenWBOInc-Py: A Python Binding for the Open-WBO-Inc MaxSAT Solver

This repository provides a Python binding for Open-WBO-Inc, an efficient incomplete MaxSAT solver originally written in C++. This binding allows you to seamlessly integrate Open-WBO-Inc's capabilities into your Python projects, offering a convenient way to tackle Maximum Satisfiability problems.

This binding is specifically for the `Open-WBO-Inc` variant of the solver. The original C++ source code for Open-WBO-Inc, along with its detailed development and research, can be found at [https://github.com/sat-group/open-wbo-inc](https://github.com/sat-group/open-wbo-inc).

## Introduction

Open-WBO-Inc is a state-of-the-art incomplete MaxSAT solver. It implements various incomplete MaxSAT algorithms and encodings, providing a robust framework for solving Weighted Boolean Satisfiability problems.

## Dependencies

Dependencies for the C++ core (some included in this repository, others are system dependencies):
- Glucose (SAT solver, included)
- GMP (GNU Multiple Precision Arithmetic Library, system dependency)

## Python Binding

### Installation

To install the `openwbo_inc_py` Python binding, clone this repository and use `pip` from the project's root directory:

```bash
git clone [YOUR_REPOSITORY_LINK] # Replace with the actual repository URL
cd open-wbo-inc
pip install .
```

If you are developing the binding and want to make changes, you can install it in editable mode:

```bash
pip install -e .
```

### Usage

Once installed, you can import the `openwbo_inc_py` module and use the `OpenWBOInc` class. The API closely mirrors the underlying C++ library's functionality.

Here's a Python example demonstrating how to create variables, add clauses (both hard and soft), solve the MaxSAT problem, and retrieve the solution:

```python
import openwbo_inc_py

# Create an OpenWBO solver instance
solver = openwbo_inc_py.OpenWBOInc()

# Create variables. newVar() returns an integer representing the variable.
# Variables are 1-indexed in OpenWBO's internal representation.
a = solver.newVar()
b = solver.newVar()
c = solver.newVar()

# Add hard clauses
# Hard clauses must always be satisfied.
# The addClause method with no weight is a hard clause.
# Note that the method is called addClause for both hard and soft clauses.
solver.addClause([-a, -b])  # Equivalent to: !a OR !b

# Add soft clauses
# Soft clauses have an associated weight. The solver tries to minimize the sum
# of weights of falsified soft clauses.
# The addClause method with a weight is a soft clause.
solver.addClause([a, b], 1)   # a OR b, with weight 1
solver.addClause([c], 1)      # c, with weight 1
solver.addClause([a, -c], 1)  # a OR !c, with weight 1
solver.addClause([b, -c], 1)  # b OR !c, with weight 1

# Solve the MaxSAT problem
# The solve() method returns True if an optimum solution is found, False otherwise.
if solver.solve():
    print("s OPTIMUM FOUND")
    # Get the minimum cost (sum of weights of falsified soft clauses)
    print(f"o {solver.getCost()}")

    # Get the value of each variable in the found solution
    # getValue(variable_id) returns True if the variable is true, False if false.
    print(f"a = {solver.getValue(a)}")
    print(f"b = {solver.getValue(b)}")
    print(f"c = {solver.getValue(c)}")
else:
    print("s UNSATISFIABLE")

```