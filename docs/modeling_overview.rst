Modelling Overview
==================

``hermax.model`` is a Python modelling layer for SAT/MaxSAT.

This page is decision oriented: what to use, when, and what workflow to follow.
For internal compilation and mutability rules, see
:doc:`modeling_internal_overview`.

Model vs Direct Solvers
-----------------------

Use :mod:`hermax.model` when your problem is easier to express with typed
variables and constraints (booleans, bounded integers, enums, intervals,
collections, PB constraints), and you want Hermax to lower that to CNF/WCNF.

Use direct solver wrappers when you already have low-level CNF/WCNF/IPAMIR
logic and want explicit control over incremental operations:

* :mod:`hermax.incremental`
* :mod:`hermax.non_incremental`

In short:

* If your thinking is at the level of "variables + constraints + objective",
  use ``Model``.
* If your thinking is already at the level of literals/clauses/assumptions and
  backend-specific calls, use the solver wrappers.

Variable and Domain Choices
---------------------------

Choose variable families by problem semantics:

* :meth:`hermax.model.Model.bool`:
  pure logical decisions.
* :meth:`hermax.model.Model.enum`:
  one-of-k categorical decisions.
* :meth:`hermax.model.Model.int`:
  bounded integer decisions.
* :meth:`hermax.model.Model.interval`:
  start/end/duration scheduling decisions.

For structured models, use containers:

* vectors: ``bool_vector``, ``enum_vector``, ``int_vector``
* matrices: ``bool_matrix``, ``enum_matrix``, ``int_matrix``
* keyed dictionaries: ``bool_dict``, ``enum_dict``, ``int_dict``

Hard vs Soft Constraints
------------------------

Hard constraints define feasibility:

* ``model &= constraint``

Soft constraints define optimization penalties:

Hermax model softs follow **WCNF / MaxSAT**:

* ``model.obj[w] += clause`` means:
  pay ``w`` **if the clause is violated**

For unit literals:

* ``model.obj[w] += a`` pays when ``a`` is false
* ``model.obj[w] += ~a`` pays when ``a`` is true

Single vs Tiered Objective
--------------------------

Use a single objective when all soft penalties belong to one scale:

* ``model.obj[w] += ...``

Use tiered objective when priorities are lexicographic and must not be mixed:

* ``model.tier_obj[tier][w] += ...``

This is useful when, for example, service-level violations must be minimized
before any secondary cost.

Solve / Export / Decode Loop
----------------------------

Typical modelling workflow:

1. Declare variables/domains
2. Add hard constraints
3. Add objective terms (single or tiered)
4. Solve or export
5. Decode typed assignments

Core calls:

* ``model.solve()``
* ``model.to_cnf()``
* ``model.to_wcnf()``
* decode via returned assignment/solve result objects

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
