Solver Subprocess Isolation
======================================

Some incomplete MaxSAT solvers are exposed through native Python bindings but
executed in a separate Python subprocess per solve.

Why this exists
---------------

Some research solvers are hard to run safely in-process because they may:

* call ``exit()``
* crash
* require hard timeout enforcement

Hermax keeps native bindings and isolates execution in a one-shot worker
process.

Architecture
------------------------------

Parent wrapper (public API)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The public wrapper in ``hermax.non_incremental.incomplete``:

* caches hard/soft clauses in Python (fake incrementality)
* accepts incremental API calls (``add_clause``, ``add_soft_unit``, etc.)
* builds a serializable snapshot on each ``solve()``
* launches a one-shot worker subprocess

Child worker
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The worker:

* imports the native binding-backed solver wrapper
* replays the snapshot into a fresh solver instance
* runs exactly one ``solve()``
* returns status/model/cost/signature, then
* exits

Timeout
-----------------

Timeouts are enforced in the **parent** process.

The child process is treated as untrusted from a control-flow perspective.

Typical timeout sequence:

1. Start worker in a dedicated process group/session.
2. Wait for response until ``timeout_s``.
3. On timeout, send a soft interrupt (``SIGINT`` / platform equivalent).
4. Wait ``timeout_grace_s``.
5. Force kill if still running.

Portfolio reuse
---------------

The same parent-side subprocess primitives are used by
:class:`hermax.portfolio.PortfolioSolver`, which runs multiple solver workers in
parallel and applies result selection and validation policies on top of the
shared one-shot worker mechanism.

Portfolio execution still uses native Python bindings in the child workers. For
public incomplete solvers, the portfolio targets the in-process worker wrapper
classes (not the public subprocess wrappers) to avoid nested subprocesses.

Assumptions And Incrementality
-----------------------------------

These wrappers are not natively incremental. Hermax emulates an IPAMIR
API by rebuilding solver state on each ``solve()``.

Assumptions are emulated by adding temporary hard unit clauses to the
snapshot sent to the worker.

Result Validation
-----------------

Some solvers occasionally report:

* a model that violates hard clauses
* an objective value inconsistent with the returned model

Hermax includes model/cost validation helpers in:

* ``hermax.internal.model_check``
