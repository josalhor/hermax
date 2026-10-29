Solve, Export, and Decode
=========================

The model layer can export PySAT formulas, decode solver models, and call
``solve()``. For API changes in 1.3, see :doc:`modeling_objective_migration`.

Export to CNF / WCNF
--------------------

Use:

* ``model.to_cnf()``
* ``model.to_wcnf()``

Rules:

* ``to_cnf()`` requires the model to contain **no soft clauses**
* ``to_wcnf()`` exports both hard and soft clauses

``to_cnf()`` raises ``ValueError`` if soft clauses are present.

Numeric objectives
------------------

``model.obj = expression`` replaces the objective.
``model.obj += expression`` adds to it. Both minimize numeric values;
Boolean literals count as 0 when false and 1 when true.

.. code-block:: python

   x = model.int("x", 0, 5)
   chosen = model.bool("chosen")
   model.obj = 3 * x
   model.obj += 5 * ~chosen   # pay 5 when chosen is false

``obj.clear()`` removes the objective. ``obj.set(expression, weight=w)``
replaces it with ``w * expression``. Negative costs are supported.
For compound Boolean conditions, see :ref:`boolean-objective-penalties`.

Lexicographic objective API
---------------------------

For strict priority optimization (tier 0 first, then tier 1, ...), use
``model.tier_obj``.

Set all priorities at once, or add costs to individual tiers:

* all priorities:

  .. code-block:: python

     model.tier_obj.set_lexicographic(primary_cost, secondary_cost)

* individual additions:

  .. code-block:: python

     model.tier_obj.add(primary_term, weight=5, tier=0)
     model.tier_obj.add(secondary_term, tier=1)

Lower tier indices have higher priority. To change an existing term, use
``model.tier_obj.update(term, weight=w)``.

Rules:

* tiers are solved in lexicographic order
* ``model.obj`` and ``model.tier_obj`` are mutually exclusive in one model state
* use ``model.tier_obj.clear()`` to drop tier objectives

Solve strategies:

* ``model.solve(lex_strategy="incremental")``: sequential lex optimization (default)
* ``model.solve(lex_strategy="stratified")``: one solve call with scaled weights

Tiered solving requires a solver class.

If stratified scaling would overflow integer bounds, solving raises a
``ValueError``/``OverflowError``; use ``lex_strategy="incremental"`` in that case.

Assumptions apply to every tier step.

Result fields:

* ``SolveResult.tier_costs``: per-tier costs (highest priority first)
* ``SolveResult.tier_models``:
  raw model for each tier in an incremental lex solve;
  ``None`` for stratified solve
* ``SolveResult.cost``:
  final-tier cost for incremental lex solve

Example:

.. code-block:: python

   m = Model()
   a = m.bool("a")
   b = m.bool("b")

   m.tier_obj.set_lexicographic(a, 10 * ~b)

   r = m.solve(lex_strategy="incremental")
   print(r.tier_costs, r.cost)

Decode solver models
--------------------

Use:

.. code-block:: python

   assignment = model.decode_model(raw_lits)

or via the convenience result object from ``Model.solve()``.

``AssignmentView`` supports decoding:

* ``Literal`` -> ``bool``
* ``EnumVar`` -> ``str | int | None``
* ``IntVar`` -> ``int``
* linear expressions -> their numeric value
* vectors -> lists
* matrices / matrix views -> nested lists
* dicts -> dicts

For example, ``result[3 * x + 2 * b]`` evaluates the expression using the
returned assignment.

Convenience Solving
-------------------

``Model.solve()`` is the main entry point and keeps backend state by default.

Behavior:

* hard-only models: incremental SAT backend (PySAT, default ``g4``)
* soft models with default ``backend="auto"`` and no explicit solver:
  one-shot Hermax RC2 path (via ``hermax.non_incremental.RC2``)
* explicit ``backend="maxsat"`` with incremental mode:
  requires a Hermax ``IPAMIRSolver`` class/factory or instance
* explicit ``solver=...`` with ``backend="auto"`` and no bound backend:
  one-shot solve through that solver

Returns :class:`hermax.model.SolveResult` with:

* ``status``
* ``ok``: whether an assignment is available
* ``proven``: whether satisfiability, unsatisfiability, or optimality was established
* ``cost`` (``None`` for SAT)
* ``raw_model``
* ``assignment`` (decoded view)

Incremental Defaults
----------------------------------------

``Model.solve()`` defaults to incremental behavior:

.. code-block:: python

   m = Model()
   a = m.bool("a")
   m.solve()      # binds SAT backend
   m &= ~a        # routed incrementally
   m.solve()

Once a backend is bound, updates are sent to it before the next solve.
Soft-clause behavior depends on bound mode:

* bound MaxSAT backend: soft additions/updates are applied on the MaxSAT side
* bound SAT backend: soft additions are cached in the model and applied when
  solving upgrades/rebinds to MaxSAT

Backend transition rules:

* SAT-bound model + newly added soft constraints:
  by default, next ``solve()`` upgrades to MaxSAT (``sat_upgrade="upgrade"``)
* use ``sat_upgrade="error"`` to make SAT->MaxSAT upgrade fail explicitly
* MaxSAT-bound model cannot switch to SAT backend

Assumptions
-----------

``Model.solve(assumptions=...)`` accepts:

* DIMACS integers (non-zero)
* ``Literal``
* unit ``Term`` (coefficient ``+1`` or ``-1``)

Examples:

.. code-block:: python

   a = m.bool("a")
   b = m.bool("b")
   r = m.solve(assumptions=[a.id, ~b, 1 * a, -1 * b])

Weight updates
--------------

``obj.add()`` returns a handle for an objective term. Use ``obj.update()`` to
change its weight:

.. code-block:: python

   x = model.int("x", 0, 5)
   term = model.obj.add(x, weight=3)
   model.obj.update(term, weight=7)

Only that term changes. Weights are non-negative; zero disables the term.
Clearing or replacing the objective invalidates its handles.

Floating objective weights
--------------------------

Set decimal precision before adding numeric costs:

.. code-block:: python

   model.set_objective_precision(decimals=2)
   model.obj = 1.25 * x

Weights are rounded to the configured precision. Without this setting, weights
must be integers. Clear the objective before changing precision.
PB/Card constraints still require integer coefficients and constants.

Hermax solver integration
-------------------------

``Model.solve()`` can use Hermax MaxSAT backends directly via the IPAMIR
solver interface defined in :mod:`hermax.core.ipamir_solver_interface`.

Supported forms:

* pass a solver **class** / factory (the model exports WCNF and the solver is
  constructed with ``formula=...``)
* pass a solver **instance** (the model is replayed into that instance through
  the IPAMIR API)

Examples:

.. code-block:: python

   from hermax.incremental.UWrMaxSAT import UWrMaxSAT

   r = m.solve(solver=UWrMaxSAT)
   print(r.status, r.cost)

.. code-block:: python

   inst = UWrMaxSAT()
   r = m.solve(solver=inst)
   inst.close()

Portfolio usage is also supported because :class:`hermax.portfolio.PortfolioSolver`
implements the same IPAMIR solver interface:

.. code-block:: python

   from hermax.portfolio import PortfolioSolver
   from hermax.incremental.UWrMaxSAT import UWrMaxSAT

   r = m.solve(
       solver=PortfolioSolver,
       solver_kwargs={
           "solver_classes": [UWrMaxSAT],
           "max_workers": 1,
           "selection_policy": "first_optimal_or_best_until_time_limit",
       },
   )

Time limits
-----------

Pass a positive number of seconds with ``time_limit`` when using a timed
one-shot solve:

.. code-block:: python

   result = m.solve(incremental=False, time_limit=10)

   if result.ok:
       print(result.status, result.cost)

When a search stops after finding an incumbent, ``result.status`` is
``"interrupted_sat"`` and the decoded assignment is available. In this case,
``result.ok`` is true but ``result.proven`` is false.

Notes:

* ``solver_kwargs`` is only valid when ``solver`` is a class/factory.
* ``backend="maxsat"`` in incremental mode requires a Hermax IPAMIR solver.
* default ``backend="auto"`` keeps one-shot Hermax RC2 for soft models.

Example
-------

.. code-block:: python

   m = Model()
   a = m.bool("a")
   b = m.bool("b")
   m &= (a | b)
   m.obj += 2 * a
   m.obj += b

   r = m.solve()
   print(r.status, r.cost)
   print(r[a], r[b])

Manual solver roundtrip
-----------------------

For explicit solver control, export and solve manually:

.. code-block:: python

   wcnf = m.to_wcnf()
   from pysat.examples.rc2 import RC2
   with RC2(wcnf) as rc2:
       raw = rc2.compute()
       assignment = m.decode_model(raw)
