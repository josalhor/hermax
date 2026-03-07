Portfolio Solver
================

The :mod:`hermax.portfolio` package provides a process-isolated solver
portfolio that can race multiple Hermax solver classes on the same MaxSAT
instance.

Unlike the incomplete-solver wrappers, the portfolio is a *general* front-end:
it accepts incremental wrappers, non-incremental wrappers, and incomplete
solvers in the same run. Each solver is executed in its own subprocess for
robustness and timeout control.

Module Description
------------------

``PortfolioSolver`` is a fake-incremental wrapper:

* it caches the formula in Python,
* records an IPAMIR-level operation log,
* replays that log into fresh worker processes on each ``solve()``,
* validates returned models/costs (enabled by default), and
* selects a final result according to a configurable policy.

Users pass Python classes directly (no string registry required in the public
API), for example:

.. code-block:: python

   from hermax.portfolio import PortfolioSolver
   from hermax.non_incremental import CGSSSolver
   from hermax.non_incremental.incomplete import Loandra, OpenWBOInc

   s = PortfolioSolver(
       [CGSSSolver, Loandra, OpenWBOInc],
       per_solver_timeout_s=5.0,
       overall_timeout_s=10.0,
       selection_policy="first_optimal_or_best_until_timeout",
   )

Preset Portfolios
-----------------

Hermax also provides auto-discovered preset portfolio subclasses:

* :class:`hermax.portfolio.CompletePortfolioSolver`
* :class:`hermax.portfolio.IncompletePortfolioSolver`
* :class:`hermax.portfolio.PerformancePortfolioSolver`

These presets discover solver classes automatically from the public namespace
structure:

* ``CompletePortfolioSolver``:
  ``hermax.incremental`` + ``hermax.non_incremental``
* ``IncompletePortfolioSolver``:
  ``hermax.non_incremental.incomplete``
* ``PerformancePortfolioSolver``:
  union of complete + incomplete namespaces

This discovery is structural and deterministic (no separate static registry is
required). Presets:

* use namespace ``__all__`` exports as the membership contract,
* keep only classes implementing :class:`hermax.core.ipamir_solver_interface.IPAMIRSolver`,
* skip abstract classes,
* de-duplicate aliases by the *effective worker class* used inside the
  subprocess (important for incomplete wrappers), and
* sort deterministically by effective worker class path.

Example (preset subclass):

.. code-block:: python

   from hermax.portfolio import PerformancePortfolioSolver

   s = PerformancePortfolioSolver(
       per_solver_timeout_s=5.0,
       overall_timeout_s=15.0,
       max_workers=4,
   )

Example (classmethod constructors):

.. code-block:: python

   from hermax.portfolio import PortfolioSolver

   s1 = PortfolioSolver.complete(max_workers=4)
   s2 = PortfolioSolver.incomplete(selection_policy="first_valid")
   s3 = PortfolioSolver.performance(
       per_solver_timeout_s=5.0,
       overall_timeout_s=15.0,
       max_workers=8,
   )

Key options
-----------

* ``selection_policy``:

  * ``"best_valid_until_timeout"``
  * ``"first_valid"``
  * ``"first_optimal_or_best_until_timeout"`` (default)

* ``max_workers`` (default ``0`` = no limit):
  maximum number of solver subprocesses run concurrently. This is a process
  concurrency limit (not an internal SAT/MaxSAT threading option).

* ``validate_model`` (default ``True``):
  reject results whose model violates hard clauses.
* ``recompute_cost_from_model`` (default ``True``):
  compute the portfolio-facing cost from the returned model using canonical
  Hermax/IPAMIR.
* ``invalid_result_policy`` (default ``"warn_drop"``):
  what to do with invalid solver outputs (warn/drop/raise/ignore).

Callback API
------------

``PortfolioSolver`` supports event-driven callbacks through
``set_callback(...)``.

Supported callback signatures:

* legacy: ``callback()``
* event form: ``callback(event)``

If the callback raises an exception, the portfolio interprets it as
``STOP``.

Events
~~~~~~

Callbacks receive :class:`hermax.portfolio.PortfolioEvent` values:

* ``event_type``:
  ``"HEARTBEAT"`` or ``"INCUMBENT"``
* ``elapsed_s``:
  time since ``solve()`` started
* ``worker_id``:
  worker index for incumbent events (``None`` for heartbeat)
* ``cost``:
  incumbent cost (if available)
* ``model``:
  incumbent model list (if available)
* ``is_optimal``:
  whether incumbent status is optimal

Heartbeat cadence defaults to 1 second.

Incumbent callbacks are emitted on strict improvements only. If multiple
improvements happen before callback dispatch, only the latest incumbent is
sent.

Actions
~~~~~~~

The callback may return:

* ``None`` or :class:`hermax.portfolio.CallbackAction.CONTINUE`
* :class:`hermax.portfolio.CallbackAction.STOP`
* :class:`hermax.portfolio.CallbackAction.DROP_CURRENT`
* :class:`hermax.portfolio.AdjustTimeout(...)`

``AdjustTimeout`` supports:

* ``mode="relative"`` (default): timeout from now
* ``mode="absolute"``: timeout from solve start

Example
~~~~~~~

.. code-block:: python

   from hermax.portfolio import (
       PortfolioSolver,
       PortfolioEvent,
       CallbackAction,
       AdjustTimeout,
   )
   from hermax.non_incremental import CGSSSolver
   from hermax.non_incremental.incomplete import Loandra

   def monitor(event: PortfolioEvent):
       if event.event_type == "HEARTBEAT":
           return
       if event.cost is not None and event.cost <= 50:
           return CallbackAction.STOP
       if event.cost is not None and event.cost <= 200:
           return AdjustTimeout(new_timeout_s=3.0, mode="relative")

   s = PortfolioSolver([CGSSSolver, Loandra], overall_timeout_s=20.0)
   s.set_callback(monitor)
   s.solve()

Behavior Notes for Presets
--------------------------

``CompletePortfolioSolver`` and ``PerformancePortfolioSolver`` are suitable
for standard IPAMIR conformance and hardcore test suites because they include
complete/reentrant backends and can produce trusted ``UNSAT``/``OPTIMUM``
results.

``IncompletePortfolioSolver`` is different by design:

* it may return valid feasible solutions without proving optimality,
* it does not guarantee trusted ``UNSAT`` classification,
* it is therefore expected to use ``PASS/SKIP`` policies for exact-optimum and
  exact-UNSAT conformance tests.

This is a contract property of the preset (not a bug): it aggregates only
incomplete solvers.

API Details
-----------

.. autoclass:: hermax.portfolio.PortfolioSolver
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.portfolio.CompletePortfolioSolver
   :members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.portfolio.IncompletePortfolioSolver
   :members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.portfolio.PerformancePortfolioSolver
   :members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.portfolio.PortfolioEvent
   :members:

.. autoclass:: hermax.portfolio.AdjustTimeout
   :members:

.. autoclass:: hermax.portfolio.CallbackAction
   :members:

Notes
-----

* The portfolio validates solver outputs to defend against known MaxSAT solver
  failure modes (invalid models, inconsistent objective reports).
* Public incomplete solvers (e.g. ``Loandra``) are mapped internally to their
  in-process worker wrapper classes when executed inside the portfolio to avoid
  nested subprocesses.
* Preset discovery is automatic and based on public namespace exports; if the
  exported solver set changes, the preset membership changes accordingly.
* For subprocess architecture details, see :doc:`incomplete_subprocess`.

References
----------

* Lin Xu, Frank Hutter, Holger H. Hoos, Kevin Leyton-Brown. *SATzilla: Portfolio-based Algorithm Selection for SAT*. JAIR 2008.
* Lin Xu, Frank Hutter, Jonathan Shen, Holger H. Hoos, Kevin Leyton-Brown. *Hydra-MIP and Hydra: Automated Algorithm Configuration and Selection*. AAAI 2010.
* Andreas Niskanen, Jeremias Berg, Matti Järvisalo. *Incremental Maximum Satisfiability*. SAT 2022.
