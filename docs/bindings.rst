Bindings Reference
==================

Documents the pybind11-level APIs exposed by Hermax C/C++ extensions. Method
names and signatures below are the exact Python-facing names exported by the
corresponding ``PYBIND11_MODULE`` definitions.

pybind11
--------------

**A big thanks to the pybind11 project**:
https://github.com/pybind/pybind11

pybind11 has made building and maintaining Hermax Python bindings
substantially simpler.

Conventions
-----------

* Literals are signed integers (DIMACS style), and literal ``0`` is invalid.
* Clause arguments are ``list[int]``.
* ``weight=None`` means hard clause; ``weight`` as integer means soft clause.
* IPAMIR-like return codes used by several bindings:

  * ``30``: optimum found
  * ``20``: unsatisfiable
  * ``10``: interrupted with feasible solution
  * ``0``: interrupted without feasible solution

UWrMaxSAT (IPAMIR)
-------------------------

Binding source: ``urmaxsat-py/python/urmaxsat_bindings.cpp``

.. py:class:: urmaxsat_py.UWrMaxSAT

   .. py:method:: newVar() -> int

      Allocate and return a fresh variable index (1-based).

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Add a clause. Hard if ``weight is None``. Soft otherwise.
      Non-unit soft clauses are internally relaxed with an auxiliary variable.

   .. py:method:: assume(assumptions: list[int]) -> None

      Add solve-time assumptions for the next ``solve()`` call.

   .. py:method:: solve() -> int

      Run the solver and return an IPAMIR status code.

   .. py:method:: getCost() -> int

      Return the current objective value.

   .. py:method:: getValue(lit: int) -> bool | None

      Return ``True`` if literal is satisfied, ``False`` if falsified, else
      ``None`` when value is unavailable.

   .. py:method:: set_terminate(callback: Callable[[], int] | None) -> None

      Install or clear termination callback.

   .. py:method:: signature() -> str

      Return backend signature string.

UWrMaxSAT
---------------------------

Binding source: ``urmaxsat-comp-py/python/urmaxsat_comp_bindings.cpp``

.. py:class:: urmaxsat_comp_py.UWrMaxSAT

   Same API as :py:class:`urmaxsat_py.UWrMaxSAT`:
   ``newVar``, ``addClause``, ``assume``, ``solve``, ``getCost``,
   ``getValue``, ``set_terminate``, ``signature``.

CASHWMaxSAT
-----------

Binding source: ``cashwmaxsat-py/python/cashwmaxsat_bindings.cpp``

.. py:class:: cashwmaxsat.CASHWMaxSAT

   .. py:method:: newVar() -> int

      Allocate and return a fresh variable index.

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Add hard/soft clause. Non-unit soft clauses are relaxed via an aux var.

   .. py:method:: setNoScip() -> None

      Disable SCIP integration in CASHWMaxSAT backend.

   .. py:method:: assume(assumptions: list[int]) -> None

      Add assumptions for next solve.

   .. py:method:: solve() -> int

      Solve and return IPAMIR status code.

   .. py:method:: getCost() -> int

      Return current objective value.

   .. py:method:: getValue(lit: int) -> bool | None

      Return literal value in current model, or ``None`` if unavailable.

   .. py:method:: set_terminate(callback: Callable[[], int] | None) -> None

      Install or clear termination callback.

   .. py:method:: signature() -> str

      Return backend signature string.


EvalMaxSAT
-----------------

Binding source: ``evalmaxsat-latest-py/python/evalmaxsat_latest_bindings.cpp``

.. py:class:: evalmaxsat_latest.EvalMaxSAT

   .. py:method:: newVar(decisionVar: bool = True) -> int

      Allocate a fresh variable (optionally as decision variable).

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> int

      Add hard or soft clause. Returns backend result code/aux identifier from
      EvalMaxSAT core.

   .. py:method:: solve() -> bool

      Solve instance; ``True`` on satisfiable/optimum state.

   .. py:method:: getCost() -> int

      Return objective value.

   .. py:method:: getValue(lit: int) -> bool

      Return truth value of literal in current model.

   .. py:method:: getModel() -> list[int]

      Return full signed assignment vector ``[±1, ±2, ...]``.

   .. py:method:: setNInputVars(n: int) -> None

      Set number of input variables in backend.

.. warning::
   EvalMaxSAT bindings are currently unstable on macOS (``arm64`` and
   ``x86_64``) and may crash on some weighted-core test patterns.

EvalMaxSAT (IPAMIR)
---------------------------------------

Binding source: ``evalmaxsat-incr-py/python/evalmaxsat_incr_bindings.cpp``

.. py:class:: evalmaxsat_incr.EvalMaxSATIncr

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Add hard clause or unit soft clause. Non-unit soft clauses raise
      ``RuntimeError`` and must be encoded via relaxation in Python.

   .. py:method:: addSoftLit(lit: int, weight: int) -> None

      Add a native soft literal term.

   .. py:method:: assume(assumptions: list[int]) -> None

      Add assumptions for next solve.

   .. py:method:: solve() -> int

      Solve and return IPAMIR status code.

   .. py:method:: getCost() -> int

      Return objective value of the last successful solve.

   .. py:method:: getValue(lit: int) -> bool | None

      Return literal truth value in current model, else ``None``.

   .. py:method:: signature() -> str

      Return backend signature string.

Open-WBO-Inc (Incomplete)
----------------------------

Binding source: ``open-wbo-inc/openwbo_bindings.cpp``

.. py:class:: openwbo_inc.OpenWBOInc

   .. py:method:: newVar() -> int

      Allocate and return a fresh variable index.

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Add hard or soft clause depending on ``weight``.

   .. py:method:: solve() -> bool

      Solve and return whether a satisfying/optimal model was produced.

   .. py:method:: getCost() -> int

      Return objective value for latest solve call.

   .. py:method:: getValue(var: int) -> bool

      Return assignment for 1-based variable ``var``.

Open-WBO Algorithms
--------------------------------------

Binding source: ``open-wbo/openwbo_bindings.cpp``

.. py:class:: openwbo.OLL
.. py:class:: openwbo.PartMSU3
.. py:class:: openwbo.Auto

   Shared API:

   .. py:method:: newVar() -> int

      Allocate fresh external variable id.

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Register clause in internal history. Validates literals and weights.

   .. py:method:: solve(assumptions: list[int] | None = None) -> bool

      Rebuild formula and solve with selected algorithm.

   .. py:method:: getCost() -> int

      Return current cost after solve.

   .. py:method:: getValue(var: int) -> bool

      Return variable assignment for 1-based ``var`` in latest model.

Loandra
-------

Binding source: ``loandra-py/python/loandra_bindings.cpp``

.. py:class:: loandra.Loandra

   .. py:method:: newVar() -> int

      Allocate and return a fresh variable index.

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Add hard or soft clause.

   .. py:method:: solve() -> bool

      Solve the current instance.

   .. py:method:: getCost() -> int

      Return objective value.

   .. py:method:: getValue(var: int) -> bool

      Return assignment for 1-based variable ``var``.

   .. py:method:: getModel() -> list[int]

      Return full signed assignment vector ``[±1, ±2, ...]``.

NuWLS-c-IBR
-----------

Binding source: ``nuwls-c-ibr-py/python/nuwls_c_ibr_bindings.cpp``

.. py:class:: nuwls_c_ibr.NuWLSCIBR

   .. py:method:: newVar() -> int

      Allocate and return a fresh variable index.

   .. py:method:: setNInputVars(n: int) -> None

      Set number of input variables used by the backend.

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Add hard or soft clause.

   .. py:method:: solve(assumptions: list[int] | None = None) -> bool

      Solve the current instance.

   .. py:method:: getCost() -> int

      Return objective value.

   .. py:method:: getValue(var: int) -> bool

      Return assignment for 1-based variable ``var``.

   .. py:method:: getModel() -> list[int]

      Return full signed assignment vector ``[±1, ±2, ...]``.

SPB-MaxSAT-c-FPS
----------------

Binding source: ``spb-maxsat-c-fps-py/python/spb_maxsat_c_fps_bindings.cpp``

.. py:class:: spb_maxsat_c_fps.SPBMaxSATCFPS

   .. py:method:: newVar() -> int

      Allocate and return a fresh variable index.

   .. py:method:: setNInputVars(n: int) -> None

      Set number of input variables used by the backend.

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Add hard or soft clause.

   .. py:method:: solve(assumptions: list[int] | None = None) -> bool

      Solve the current instance.

   .. py:method:: getCost() -> int

      Return objective value.

   .. py:method:: getValue(var: int) -> bool

      Return assignment for 1-based variable ``var``.

   .. py:method:: getModel() -> list[int]

      Return full signed assignment vector ``[±1, ±2, ...]``.

WMaxCDCL
--------

Binding source: ``wmaxcdcl-py/python/wmaxcdcl_bindings.cpp``

.. py:class:: wmaxcdcl.WMaxCDCL

   .. py:method:: newVar(decisionVar: bool = True) -> int

      Allocate and return a fresh variable index.

   .. py:method:: addClause(clause: list[int], weight: int | None = None) -> None

      Add hard or soft clause.

   .. py:method:: setNInputVars(n: int) -> None

      Set number of input variables used by the backend.

   .. py:method:: prepare() -> None

      Prepare internal state before solving.

   .. py:method:: solve(assumptions: list[int] | None = None) -> bool

      Solve the current instance.

   .. py:method:: getCost() -> int

      Return objective value.

   .. py:method:: getValue(var: int) -> bool

      Return assignment for 1-based variable ``var``.

   .. py:method:: getModel() -> list[int]

      Return full signed assignment vector ``[±1, ±2, ...]``.


References
----------

* Marek Piotrów. *UWrMaxSat: Efficient Solver for MaxSAT and Pseudo-Boolean Problems*. ICTAI 2020.
* Florent Avellaneda. *EvalMaxSAT*. MaxSAT Evaluation: Solver and Benchmark Descriptions, 2023.
* Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva. *RC2: An Efficient MaxSAT Solver*. JSAT 11(1), 2019.
* Ruben Martins, Vasco Manquinho, Ines Lynce. *Open-WBO: A Modular MaxSAT Solver*. SAT 2014.
* Aditya Joshi, Ruben Martins, Vasco Manquinho. *Open-WBO-Inc: An Incremental MaxSAT Solver*. JSAT 11(1), 2019.
* Xiangyu Jiang et al. *Enhancing Diversity and Intensity in Local Search for (Weighted) Partial MaxSAT*. SAT 2025.
* Jiayi Chu, Chuan Luo, et al. *NuWLS-c-IBR*. MaxSAT Evaluation solver description, 2023.
* K. Lübke, A. Niskanen. *Loandra: Local Search Meets Core-Guided MaxSAT*. MaxSAT Evaluation solver description, 2025.
