Solve, Export, and Decode
=========================

The model layer supports export to PySAT formulas, decoding, and ``solve()``.

Export to CNF / WCNF
--------------------

Use:

* ``model.to_cnf()``
* ``model.to_wcnf()``

Rules:

* ``to_cnf()`` requires the model to contain **no soft clauses**
* ``to_wcnf()`` exports both hard and soft clauses

``to_cnf()`` raises ``ValueError`` if soft clauses are present.

Soft clauses
--------------------------------

``model.obj[w] += constraint`` adds weighted soft clauses.

For a unit literal ``a``:

* ``model.obj[5] += a`` means pay ``5`` if ``a`` is false
* ``model.obj[5] += ~a`` means pay ``5`` if ``a`` is true

Objective replacement
-------------------------

The objective has two modes:

* additive mode via ``model.obj += ...`` and ``model.obj[w] += ...``
* replacement mode via ``model.obj = expr`` (or ``model.obj.set(expr)``)

Replacement mode clears active objective terms and installs the new objective.
Additive mode keeps previous objective terms.

Use:

.. code-block:: python

   m = Model()
   a = m.bool("a")
   b = m.bool("b")

   m.obj[3] += a        # additive
   m.obj[2] += ~b       # additive
   m.obj = (a + 5)      # replace objective
   m.obj.clear()        # remove objective terms managed by replacement API

Notes:

* ``model.obj = expr`` expects a linear expression
  (``Literal``, ``Term``, ``PBExpr``, ``IntVar``, lazy int expr)
* for literal/clause soft constraints, use additive APIs
  (``obj +=``, ``obj[w] +=``, or ``add_soft``)

Lexicographic objective API
---------------------------

For strict priority optimization (tier 0 first, then tier 1, ...), use
``model.tier_obj``.

Two declaration styles are supported:

* declarative:

  .. code-block:: python

     model.tier_obj.set_lexicographic(primary_cost, secondary_cost)

* dynamic:

  .. code-block:: python

     model.tier_obj[0, 5] += primary_term
     model.tier_obj[1, 1] += secondary_term

Rules:

* lower tier index means higher priority
* tiers are solved in lexicographic order
* ``model.obj``/``add_soft`` and ``model.tier_obj`` are mutually exclusive in one model state
* use ``model.tier_obj.clear()`` to drop tier objectives

Solve strategies:

* ``model.solve(lex_strategy="incremental")``: sequential lex optimization (default)
* ``model.solve(lex_strategy="stratified")``: one solve call with scaled weights

If stratified scaling would overflow integer bounds, solving raises a
``ValueError``/``OverflowError``; use ``lex_strategy="incremental"`` in that case.

Assumptions apply to the whole lex query and are used for every tier step.

Result fields:

* ``SolveResult.tier_costs``: per-tier costs (highest priority first)
* ``SolveResult.tier_models``:
  per-tier raw models for incremental lex solve;
  ``None`` for stratified solve
* ``SolveResult.cost``:
  final-tier cost for incremental lex solve

Example:

.. code-block:: python

   m = Model()
   a = m.bool("a")
   b = m.bool("b")

   m.tier_obj[0, 1] += a      # tier 0
   m.tier_obj[1, 10] += ~b    # tier 1

   r = m.solve(lex_strategy="incremental")
   print(r.tier_costs, r.cost)

Soft groups and PB constraints
------------------------------

If the soft object compiles to multiple clauses (for example a PB constraint),
the model uses **targeted relaxation**:

* one weighted soft penalty literal
* plus the compiled clause network conditional as hard constraints

This preserves penalty per logical constraint.

Integer objective terms
------------------------------

``obj[w] += int_var`` is supported and lowered to weighted soft unit clauses on
the ladder bits (plus a constant objective offset for the lower bound).

This is restricted to ``int_var.lb >= 0``.

Decode solver models
--------------------

Use:

.. code-block:: python

   assignment = model.decode_model(raw_lits)

or via the convenience result object from ``Model.solve()``.

``AssignmentView`` supports decoding:

* ``Literal`` -> ``bool``
* ``EnumVar`` -> ``str | None``
* ``IntVar`` -> ``int``
* vectors -> lists
* matrices / matrix views -> nested lists
* dicts -> dicts

Convenience Solving
-------------------

``Model.solve()`` is the main entry point and uses model-native incremental
state by default.

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

Once a backend is bound, hard-clause updates are routed immediately.
Soft-clause behavior depends on bound mode:

* bound MaxSAT backend: soft additions/updates are routed immediately
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

Weight Updates
-------------------------------

``Model.add_soft(...)`` returns a :class:`hermax.model.SoftRef`:

* ``group_id``: logical soft group identifier
* ``soft_ids``: concrete lowered soft clause ids

Use ``update_soft_weight(target, w)`` with:

* ``SoftRef`` (recommended)
* one soft id (``int``)
* sequence of soft ids

Example:

.. code-block:: python

   x = m.int("x", 0, 5)
   ref = m.add_soft(x, 3)   # may lower into many soft clauses
   m.update_soft_weight(ref, 7)

Weight updates use positive weights in the public API.
Zero-weight removal is used internally by objective replacement and diffing.

Floating objective weights
--------------------------

Floating weights are supported for objective APIs when objective precision is
enabled:

.. code-block:: python

   m = Model()
   x = m.bool("x")
   m.set_objective_precision(decimals=2)

   m.obj = 3.5 * x
   m.obj[1.25] += ~x
   ref = m.add_soft(x, 2.75)
   m.update_soft_weight(ref, 4.10)

Rules:

* precision is disabled by default
* with precision disabled, objective weights must be integer
  (floats such as ``1.0`` are rejected)
* with precision enabled, soft/objective float weights are rounded to the
  configured decimal precision
* changing precision re-rounds existing objective soft weights from their
  original raw values

Float coefficients are not allowed in PB/Card constraints.

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
           "selection_policy": "first_optimal_or_best_until_timeout",
       },
   )

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
   m.obj[2] += ~a
   m.obj[1] += ~b

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
