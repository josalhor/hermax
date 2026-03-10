Non-Incremental Solvers
=======================

List of Classes
---------------

.. autosummary::
   :nosignatures:

   hermax.non_incremental.RC2
   hermax.non_incremental.UWrMaxSATCompetition
   hermax.non_incremental.EvalMaxSAT
   hermax.non_incremental.CASHWMaxSAT
   hermax.non_incremental.CGSS
   hermax.non_incremental.CGSSPMRES
   hermax.non_incremental.OpenWBOOLL
   hermax.non_incremental.OpenWBOPartMSU3
   hermax.non_incremental.OpenWBO
   .. hermax.non_incremental.CASHWMaxSATNoSCIP

Module Description
------------------

This module groups wrappers and re-entrant adapters used when a backend is
invoked in a non-native-incremental workflow,
while exposing the common Hermax interface.

For incomplete / subprocess-isolated wrappers (e.g. ``SPB``, ``NuWLS-c-IBR``,
``Loandra``, ``OpenWBOInc`` in their incomplete namespace placement), see
:doc:`non_incremental_incomplete` and the developer note :doc:`incomplete_subprocess`.

Backend mapping:

* :class:`hermax.non_incremental.RC2`:
  ``hermax.core.rc2.RC2Reentrant`` (re-encoding wrapper around RC2 [1]_ [2]_).
* :class:`hermax.non_incremental.UWrMaxSATCompetition`:
  ``hermax.core.uwrmaxsat_comp_py.UWrMaxSATCompReentrant`` [4]_.
* :class:`hermax.non_incremental.EvalMaxSAT`:
  ``hermax.core.evalmaxsat_latest_py.EvalMaxSATLatestReentrant`` [5]_.
* :class:`hermax.non_incremental.CASHWMaxSAT`:
  ``hermax.core.cashwmaxsat_py.CASHWMaxSATSolver`` [6]_.

.. * :class:`hermax.non_incremental.CASHWMaxSATNoSCIP`:
..   same backend as CASHWMaxSAT with SCIP disabled (adapter mode).

* :class:`hermax.non_incremental.CGSS`:
  ``hermax.core.cgss_py.CGSSSolver`` (vendored RC2WCE/CGSS wrapper [7]_).
* :class:`hermax.non_incremental.CGSSPMRES`:
  ``hermax.core.cgss_py.CGSSPMRESSolver`` (vendored PMRES variant [7]_).
* :class:`hermax.non_incremental.OpenWBOOLL`:
  ``hermax.core.openwbo_py.OLLSolver`` (Open-WBO OLL backend).
* :class:`hermax.non_incremental.OpenWBOPartMSU3`:
  ``hermax.core.openwbo_py.PartMSU3Solver`` (Open-WBO PartMSU3 backend).
* :class:`hermax.non_incremental.OpenWBO`:
  ``hermax.core.openwbo_py.AutoOpenWBOSolver`` (Open-WBO auto routing: OLL/PartMSU3/MSU3).

.. warning::
   In Hermax package builds, ``UWrMaxSATCompetition`` and  ``CASHWMaxSAT`` is compiled with SCIP
   disabled.

.. warning::
   ``hermax.non_incremental.EvalMaxSAT`` is currently unstable on macOS
   (both ``arm64`` and ``x86_64``) and may crash on some weighted-core
   instances.

API Details
-----------

.. autoclass:: hermax.non_incremental.RC2
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.UWrMaxSATCompetition
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.EvalMaxSAT
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.CASHWMaxSAT
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. .. autoclass:: hermax.non_incremental.CASHWMaxSATNoSCIP
..    :members:
..    :inherited-members:
..    :undoc-members:
..    :show-inheritance:
..    :special-members: __init__

.. autoclass:: hermax.non_incremental.CGSS
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.CGSSPMRES
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.OpenWBOOLL
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.OpenWBOPartMSU3
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: hermax.non_incremental.OpenWBO
   :members:
   :inherited-members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

References
----------

.. [1] Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva. *RC2: An Efficient MaxSAT Solver*. JSAT 11(1), 2019.
.. [2] Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva. *PySAT: A Python Toolkit for Prototyping with SAT Oracles*. SAT 2018.
.. [4] Marek Piotrów. *UWrMaxSat: Efficient Solver for MaxSAT and Pseudo-Boolean Problems*. ICTAI 2020.
.. [5] Florent Avellaneda. *EvalMaxSAT*. MaxSAT Evaluation: Solver and Benchmark Descriptions, 2023.
.. [6] Shiwei Pan, Yiyuan Wang, Shaowei Cai. *An Efficient Core-Guided Solver for Weighted Partial MaxSAT*. IJCAI 2025.
.. [7] certified-cgss project (RC2WCE/CGSS implementation), vendored integration in Hermax.
