Modelling Overview
==================

``hermax.model`` is a Python modelling layer for SAT/MaxSAT.

This page explains what to use and when.
For internal compilation and mutability rules, see
:doc:`modeling_internal_overview`.

Model vs Direct Solvers
-----------------------

Use :mod:`hermax.model` when your problem is easier to express with typed
variables and constraints (booleans, bounded integers, enums, intervals,
collections, PB constraints), and you want Hermax to lower that to CNF/WCNF.

Use direct solver wrappers when you already have low level CNF/WCNF/IPAMIR
logic and want explicit control over incremental operations:

* :mod:`hermax.incremental`
* :mod:`hermax.non_incremental`

In short:

* If your thinking is at the level of "variables + constraints + objective",
  use ``Model``.
* If your thinking is already at the level of literals/clauses/assumptions and
  backend specific calls, use the solver wrappers.

Variable and Domain Choices
---------------------------

Choose variable families by problem structure:

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

Objectives minimize numeric costs:

* ``model.obj += w * a`` pays ``w`` when ``a`` is true.
* ``model.obj += w * ~a`` pays ``w`` when ``a`` is false.
* ``model.obj = cost`` replaces the objective with a numeric expression.

See :ref:`boolean-objective-penalties` for compound Boolean penalties.

Single vs Tiered Objective
--------------------------

Use a single objective when all costs belong to one scale:

* ``model.obj += expression``

Use tiered objectives when priorities are lexicographic:

* ``model.tier_obj.set_lexicographic(primary_cost, secondary_cost)``
* ``model.tier_obj.add(cost, weight=w, tier=tier)`` for dynamic additions

Use this when, for example, service-level violations must be minimized
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
   https://pypi.org/project/PuLP/ 
.. [2] Matthew J. Saltzman. *Coin-or: an open-source library for optimization*.
   In *Programming languages and systems in computational economics and finance*,
   pages 3-32. Springer, 2002.
.. [3] Google LLC. *CP-SAT Solver, OR-Tools Documentation*.
   Google, 2024.
   https://developers.google.com/optimization/cp/cp_solver
.. [4] Google LLC. *Google OR-Tools*, version 9.15.6755, 2026.
   https://pypi.org/project/ortools/ 
