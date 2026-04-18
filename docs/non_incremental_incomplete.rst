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
   hermax.non_incremental.incomplete.TTOpenWBOInc
   hermax.non_incremental.incomplete.SPBMaxSATCFPS
   hermax.non_incremental.incomplete.NuWLSCIBR
   hermax.non_incremental.incomplete.Loandra

Backend mapping
---------------

* :class:`hermax.non_incremental.incomplete.OpenWBOInc`
  uses the native binding ``hermax.core.openwbo_inc`` and a subprocess-isolated
  wrapper in ``hermax.core.openwbo_inc_py.openwbo_inc_subprocess``.
* :class:`hermax.non_incremental.incomplete.TTOpenWBOInc`
  uses the native binding ``hermax.core.tt_openwbo_inc`` and a subprocess-isolated
  wrapper in ``hermax.core.tt_openwbo_inc_py.tt_openwbo_inc_subprocess``.
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

.. autoclass:: hermax.non_incremental.incomplete.TTOpenWBOInc
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

* Mingming Jin, Kun He, Jiongzhi Zheng, Jinghui Xue, Zhuo Chen. *Combining BandMaxSAT and FPS with SPB-MaxSAT-c*. MaxSAT Evaluation 2024: Solver and Benchmark Descriptions, 2024.
* Ruben Martins, Vasco Manquinho, Ines Lynce. *Open-WBO: A Modular MaxSAT Solver*. SAT 2014.
* Saurabh Joshi, Prateek Kumar, Sukrut Rao, Ruben Martins. *Open-WBO-Inc: Approximation Strategies for Incomplete Weighted MaxSAT*. Journal on Satisfiability, Boolean Modelling and Computation 11(1), 2019.
* Alexander Nadel. *TT-Open-WBO-Inc: an efficient anytime MaxSAT solver*. Journal on Satisfiability, Boolean Modelling and Computation 15(1), 2024.
* Alexander Nadel. *Polarity and Variable Selection Heuristics for SAT-Based Anytime MaxSAT: System Description*. Journal on Satisfiability, Boolean Modelling and Computation 12(1), 2020.
* Jeremias Berg, Emir Demirovic, Peter J. Stuckey. *Core-Boosted Linear Search for Incomplete MaxSAT*. CPAIOR 2019.
* Menghua Jiang. *NuWLS-c-IBR*. MaxSAT Evaluation solver description, 2023.
