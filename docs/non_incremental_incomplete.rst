Incomplete Non-Incremental Solvers
==================================

Documents the solvers in
``hermax.non_incremental.incomplete``.

These solvers are:

* non-IPAMIR-native (they do not provide native incremental state reuse)
* incomplete (they may return a non optimal solution)

For this reason, callers should expect :class:`hermax.core.ipamir_solver_interface.SolveStatus`
values such as ``INTERRUPTED_SAT`` for valid but non-proven solutions.

Module Description
------------------

The ``hermax.non_incremental.incomplete`` namespace contains fake-incremental
wrappers that cache the formula in Python and rebuild it on each ``solve()``.
Current implementations use subprocess isolation around native Python bindings
to tolerate solver ``exit()`` behavior and provide robust timeouts.

Available classes
-----------------

.. autosummary::
   :nosignatures:

   hermax.non_incremental.incomplete.OpenWBOInc
   hermax.non_incremental.incomplete.SPBMaxSATCFPS
   hermax.non_incremental.incomplete.NuWLSCIBR
   hermax.non_incremental.incomplete.Loandra

Backend mapping
---------------

* :class:`hermax.non_incremental.incomplete.OpenWBOInc`
  uses the native binding ``hermax.core.openwbo_inc`` and a subprocess-isolated
  wrapper in ``hermax.core.openwbo_inc_py.openwbo_inc_subprocess``.
* :class:`hermax.non_incremental.incomplete.SPBMaxSATCFPS`
  uses the native binding ``hermax.core.spb_maxsat_c_fps`` and a subprocess-isolated
  wrapper in ``hermax.core.spb_maxsat_c_fps_py.spb_maxsat_c_fps_subprocess``.
* :class:`hermax.non_incremental.incomplete.NuWLSCIBR`
  uses the native binding ``hermax.core.nuwls_c_ibr`` and a subprocess-isolated
  wrapper in ``hermax.core.nuwls_c_ibr_py.nuwls_c_ibr_subprocess``.
* :class:`hermax.non_incremental.incomplete.Loandra`
  uses the native binding ``hermax.core.loandra`` and a subprocess-isolated
  wrapper in ``hermax.core.loandra_py.loandra_subprocess``.

API Details
-----------

.. autoclass:: hermax.non_incremental.incomplete.OpenWBOInc
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.incomplete.SPBMaxSATCFPS
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.incomplete.NuWLSCIBR
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.incomplete.Loandra
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Notes
-----

* Assumptions are emulated by adding temporary hard unit clauses to the
  one-shot solve snapshot.
* Hermax recomputes costs from the returned model in several
  wrappers to protect against solver bugs.

References
----------

* Ruben Martins, Vasco Manquinho, Ines Lynce. *Open-WBO: A Modular MaxSAT Solver*. SAT 2014.
* Aditya Joshi, Ruben Martins, Vasco Manquinho. *Open-WBO-Inc: An Incremental MaxSAT Solver*. JSAT 11(1), 2019.
* Xiangyu Jiang et al. *Enhancing Diversity and Intensity in Local Search for (Weighted) Partial MaxSAT*. SAT 2025.
* Jiayi Chu, Chuan Luo, et al. *NuWLS-c-IBR*. MaxSAT Evaluation solver description, 2023.
* K. Lübke, A. Niskanen. *Loandra: Local Search Meets Core-Guided MaxSAT*. MaxSAT Evaluation solver description, 2025.
