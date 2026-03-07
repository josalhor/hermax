Solver Interface
================

List of Classes and Helpers
---------------------------

.. autosummary::
   :nosignatures:

   hermax.core.ipamir_solver_interface.SolveStatus
   hermax.core.ipamir_solver_interface.IPAMIRSolver
   hermax.core.ipamir_solver_interface.is_feasible
   hermax.core.ipamir_solver_interface.is_final

Module Description
------------------

This module defines the canonical Python-level contract implemented by Hermax
solvers through :class:`hermax.core.ipamir_solver_interface.IPAMIRSolver`.
The contract is an adaptation of the incremental MaxSAT interface proposed by
IPAMIR [1]_ and rooted in the assumption-based incremental SAT model [2]_ [3]_.

At a high level, the interface separates:

* hard constraints via ``add_clause``,
* optimization terms via ``set_soft`` / ``add_soft_unit`` / ``add_soft_relaxed``,
* per-call assumptions via ``solve(assumptions=...)``,
* result/status introspection via ``get_status``, ``get_cost``, and ``get_model``.

This explicit split is important for incremental MaxSAT, where assumptions and
weight updates can vary between calls while preserving part of the solver state
and learned information [1]_ [4]_ [5]_.

Status
----------------

:class:`hermax.core.ipamir_solver_interface.SolveStatus` follows IPAMIR-style
status codes and distinguishes three categories:

* feasible but not necessarily optimal (``INTERRUPTED_SAT``),
* final (``UNSAT`` and ``OPTIMUM``),
* abnormal/intermediate states (``INTERRUPTED``, ``ERROR``, ``UNKNOWN``).

Use :func:`hermax.core.ipamir_solver_interface.is_feasible` and
:func:`hermax.core.ipamir_solver_interface.is_final` to write backend-agnostic
control flow over multiple solvers.

IPAMIRSolver API Details
------------------------

.. autoclass:: hermax.core.ipamir_solver_interface.IPAMIRSolver
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

SolveStatus API Details
-----------------------

.. autoclass:: hermax.core.ipamir_solver_interface.SolveStatus
   :members:
   :undoc-members:
   :show-inheritance:

Helper Functions
----------------

.. autofunction:: hermax.core.ipamir_solver_interface.is_feasible

.. autofunction:: hermax.core.ipamir_solver_interface.is_final

References
----------

.. [1] Andreas Niskanen, Jeremias Berg, Matti Järvisalo. *Incremental Maximum Satisfiability*. SAT 2022.
.. [2] Niklas Eén, Niklas Sörensson. *An Extensible SAT-solver*. SAT 2003.
.. [3] Tomas Balyo, Armin Biere. *IPASIR: The Standard Interface for Incremental Satisfiability Solving*. https://github.com/biotomas/ipasir
.. [4] Xujie Si, Xin Zhang, Vasco Manquinho, Mikolás Janota, Alexey Ignatiev, Mayur Naik. *On Incremental Core-Guided MaxSAT Solving*. CP 2016.
.. [5] Alexey Ignatiev, Yacine Izza, Peter J. Stuckey, Joao Marques-Silva. *Using MaxSAT for Efficient Explanations of Tree Ensembles*. AAAI 2022.
