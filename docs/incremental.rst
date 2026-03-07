Incremental Solvers
===================

List of Classes
---------------

.. autosummary::
   :nosignatures:

   hermax.incremental.UWrMaxSAT
   hermax.incremental.UWrMaxSATCompetition
   hermax.incremental.EvalMaxSAT
   hermax.incremental.EvalMaxSATIncremental

Module Description
------------------

This module exposes Hermax classes backed by solvers that are used through an
incremental/IPAMIR-style workflow, i.e., repeated solve calls while preserving
internal state and/or interface state [1]_.

The classes map to the following backends:

* :class:`hermax.incremental.UWrMaxSAT`:
  ``hermax.core.uwrmaxsat_py.UWrMaxSATSolver`` (UWrMaxSAT family [2]_).
* :class:`hermax.incremental.UWrMaxSATCompetition`:
  ``hermax.core.uwrmaxsat_comp_py.UWrMaxSATCompSolver`` (competition branch of UWrMaxSAT [2]_).
* :class:`hermax.incremental.EvalMaxSAT`:
  ``hermax.core.evalmaxsat_latest_py.EvalMaxSATLatestSolver`` (EvalMaxSAT family [3]_).
* :class:`hermax.incremental.EvalMaxSATIncremental`:
  ``hermax.core.evalmaxsat_incr_py.EvalMaxSATIncrSolver`` (incremental EvalMaxSAT backend [3]_).

.. warning::
   EvalMaxSAT backends are currently unstable on macOS (both ``arm64`` and
   ``x86_64``) and may crash in some weighted-core workflows.
   Prefer other backends on macOS until this is fixed.

Incremental MaxSAT Landscape
----------------------------

Incremental MaxSAT behavior differs substantially across solver families [1]_:

* UWrMaxSAT is a SAT/PB-oriented line with strong MaxSAT performance and
  support for iterative optimization workflows [2]_.
* EvalMaxSAT uses an engineering strategy centered on robust state management
  in evaluation settings [3]_.

These differences are directly relevant to Hermax users: methods such as
``set_soft`` and assumption-based ``solve`` can have solver-specific internal
costs, even when the public API is uniform.

API Details
-----------

.. autoclass:: hermax.incremental.UWrMaxSAT
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.incremental.UWrMaxSATCompetition
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.incremental.EvalMaxSAT
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.incremental.EvalMaxSATIncremental
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

References
----------

.. [1] Andreas Niskanen, Jeremias Berg, Matti Järvisalo. *Incremental Maximum Satisfiability*. SAT 2022.
.. [2] Marek Piotrów. *UWrMaxSat: Efficient Solver for MaxSAT and Pseudo-Boolean Problems*. ICTAI 2020.
.. [3] Florent Avellaneda. *EvalMaxSAT*. MaxSAT Evaluation: Solver and Benchmark Descriptions, 2023.
