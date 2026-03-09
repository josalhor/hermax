Modelling Overview
==================

``hermax.model`` is a Python modelling layer for SAT/MaxSAT.

The API is strict in that:

* Expressions are evaluated immediately
* Unsupported operations fail early with explicit errors
* The ``Model`` object is the only mutable sink for constraints/objectives

Core ideas
----------

The modelling API has three main layers:

1. **Description objects** (immutable by operator)

   * :class:`hermax.model.Literal`
   * :class:`hermax.model.Clause`
   * :class:`hermax.model.ClauseGroup`
   * :class:`hermax.model.Term`
   * :class:`hermax.model.PBExpr`
   * :class:`hermax.model.PBConstraint`

2. **Typed variables / containers**

   * Booleans, enums, bounded integers
   * Vectors, matrices, keyed dictionaries

3. **Model accumulation and solving**

   * ``model &= ...`` for hard constraints
   * ``model.obj[w] += ...`` for weighted soft constraints
   * ``model.tier_obj[...] += ...`` for lexicographic (tiered) objectives
   * ``model.to_cnf()``, ``model.to_wcnf()``, ``model.solve()``

Eager vs. lazy evaluation
-----------------------------------------

The API is immediate, but not everything is compiled at the same time:

* Boolean operators produce clauses/groups immediately.
* PB comparisons produce a **lazy** :class:`hermax.model.PBConstraint`.
* The PB constraint compiles to CNF only when:

  * Added to the model (``model &= ...``),
  * Added as a soft constraint (``model.obj[w] += ...``), or
  * Explicitly requested via ``pb_constraint.clauses()``.

This keeps the design expressive while preserving enough PB metadata for safe
operations like ``PB.implies(literal)``.

Mutability contract
-------------------

Operator syntax is **immutable by contract** for modelling objects:

* ``ClauseGroup &= ...`` returns a new ``ClauseGroup`` (it does not mutate).
* ``PBExpr += ...`` returns a new ``PBExpr`` (it does not mutate).

The only intended mutable sinks are:

* ``model &= constraint``
* ``model.obj[w] += constraint``

Inplace Mutation APIs
----------------------

For performance-oriented or builder-style code, the model exposes explicit
mutators with a mandatory keyword guard:

* ``clause.append(lit, inplace=True)``
* ``group.extend(x, inplace=True)``
* ``expr.add(x, inplace=True)``
* ``expr.sub(x, inplace=True)``

Soft constraint
-------------------------

Hermax model softs follow **WCNF / MaxSAT**:

* ``model.obj[w] += clause`` means:
  pay ``w`` **if the clause is violated**

For unit literals:

* ``model.obj[w] += a`` pays when ``a`` is false
* ``model.obj[w] += ~a`` pays when ``a`` is true

Modelling References
-----------------------------

The Hermax modelling layer is inspired by established optimization and CP
tooling patterns, including PuLP [1]_, COIN-OR [2]_, and OR-Tools / CP-SAT
[3]_ [4]_.

.. [1] J. S. Roy, Stuart A. Mitchell, and PuLP contributors.
   *PuLP*, version 3.3.0, 2025.
   https://pypi.org/project/PuLP/ (accessed 2026-02-22).
.. [2] Matthew J. Saltzman. *Coin-or: an open-source library for optimization*.
   In *Programming languages and systems in computational economics and finance*,
   pages 3-32. Springer, 2002.
.. [3] Google LLC. *CP-SAT Solver, OR-Tools Documentation*.
   Google, 2024.
   https://developers.google.com/optimization/cp/cp_solver
   (accessed 2026-02-22).
.. [4] Google LLC. *Google OR-Tools*, version 9.15.6755, 2026.
   https://pypi.org/project/ortools/ (accessed 2026-02-22).
