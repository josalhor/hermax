Incremental Solvers
===================

List of Classes
---------------

.. autosummary::
   :nosignatures:

   hermax.incremental.CoreTrail
   hermax.incremental.UWrMaxSAT
   hermax.incremental.UWrMaxSATCompetition
   hermax.incremental.EvalMaxSAT
   hermax.incremental.EvalMaxSATIncremental
   hermax.incremental.IMaxHS

Module Description
------------------

This module exposes Hermax classes backed by solvers that are used through an
incremental/IPAMIR workflow, i.e., repeated solve calls while preserving
internal state and/or interface state [1]_.

CoreTrail is Hermax's default MaxSAT backend. Developed as part of Hermax,
it is a native core-guided solver designed for related incremental queries [5]_.
Its state can be reused across changes and interrupted queries can be resumed.

The classes map to the following backends:

* :class:`hermax.incremental.UWrMaxSAT`:
  ``hermax.core.uwrmaxsat_py.UWrMaxSATSolver`` (UWrMaxSAT family [2]_).
* :class:`hermax.incremental.UWrMaxSATCompetition`:
  ``hermax.core.uwrmaxsat_comp_py.UWrMaxSATCompSolver`` (competition branch of UWrMaxSAT [2]_).
* :class:`hermax.incremental.EvalMaxSAT`:
  ``hermax.core.evalmaxsat_latest_py.EvalMaxSATLatestSolver`` (EvalMaxSAT family [3]_).
* :class:`hermax.incremental.EvalMaxSATIncremental`:
  ``hermax.core.evalmaxsat_incr_py.EvalMaxSATIncrSolver`` (incremental EvalMaxSAT backend [3]_).
* :class:`hermax.incremental.IMaxHS`:
  ``hermax.core.imaxhs_wrapper_py.IMaxHSSolver`` (optional CPLEX-backed iMaxHS backend [4]_).
* :class:`hermax.incremental.CoreTrail`:
  ``hermax.core.coretrail_py.CoreTrailSolver``, a native core-guided MaxSAT
  backend that preserves its search state across assumptions, hard-clause
  additions, soft-weight updates, and interrupted solves.

.. warning::
   In Hermax package builds, both ``UWrMaxSAT`` and ``UWrMaxSATCompetition``
   are compiled with SCIP integration disabled.

.. warning::
   On Windows and macOS, preprocessing is disabled for
   ``UWrMaxSATCompetition`` due to upstream undefined behavior (UB) that can
   cause native crashes.

.. warning::
   On macOS, preprocessing is disabled for EvalMaxSAT backends due to
   possible native crashes.

Incremental MaxSAT
------------------

Incremental MaxSAT behavior differs substantially across solver families [1]_:

* UWrMaxSAT is a trutly incremental MaxSAT solver based on PB optimization [2]_.
* EvalMaxSAT uses a copy and re-solve strategy [3]_.
* CoreTrail keeps native core-guided state and supports cooperative
  ``time_limit`` interruption followed by a later resume of the same query.


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

.. autoclass:: hermax.incremental.IMaxHS
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.incremental.CoreTrail
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
.. [4] Andreas Niskanen, Jeremias Berg, Matti Järvisalo. *Enabling Incrementality in the Implicit Hitting Set Approach to MaxSAT Under Changing Weights*. CP 2021.
.. [5] Josep Maria Salvia Hornos, Alexey Ignatiev, Joao Marques-Silva.
   *CoreTrail and ShareTrail: Incremental Core-Guided MaxSAT Solvers*.
   MaxSAT Evaluation 2026: Solver and Benchmark Descriptions, p. 17.
   University of Helsinki, 2026. https://hdl.handle.net/10138/640150
