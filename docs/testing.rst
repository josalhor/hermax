Testing
=======

Hermax ships with three complementary testing layers:

1. A centralized compliance matrix runner for solver regression tracking.
2. A grammar-aware fuzzing + delta-debugging workflow for bug discovery.
3. A randomized runner over real benchmark instances.

Test Entrypoints
----------------

Primary local entrypoint:

.. code-block:: bash

   python tests/run_compliance_matrix.py --timeout 180

Wheel/CI entrypoint used by cibuildwheel:

.. code-block:: bash

   python tests/cibw_test_entrypoint.py

The wheel entrypoint delegates to the compliance matrix policy configured in
``pyproject.toml``.

Compliance Matrix
-----------------

Use the unified runner:

.. code-block:: bash

   python tests/run_compliance_matrix.py --timeout 180

Useful flags:

* ``--timeout``: per-solver timeout in seconds.
* ``--exhaustive`` / ``--no-exhaustive``: include or skip solver x test detail matrix.
* ``--out-dir``: output directory for reports and logs.
* ``--ci-policy {none,solver-pass,pass-skip,expectations}``: CI gating mode.
* ``--expectations-file``: JSON policy file for ``expectations`` mode.

Main artifacts (default: ``tests/_compliance/``):

* ``solver_matrix.csv`` / ``solver_matrix.md``
* ``solver_status_counts.csv`` / ``solver_status_counts.md``
* ``solver_x_test_matrix.csv`` / ``solver_x_test_matrix.md`` (exhaustive mode)
* ``compliance_report.json``
* ``logs/<solver>.log``

Status:

* ``PASS``: all selected tests for that solver passed.
* ``SKIP``: test or solver was skipped/unavailable.
* ``ERR``: pytest failures/errors.
* ``CRASH``: abnormal process termination.
* ``TIMEOUT``: solver run exceeded timeout.

``pass-skip`` policy is stricter than ``solver-pass``: it also requires every
solver x test entry to be either ``PASS`` or ``SKIP``.

Fuzzing And Delta Debugging
---------------------------

Hermax's fuzzing and reduction workflow follows modern MaxSAT fuzzing and
delta-debugging practice [1]_.

Run the fuzzing entrypoint:

.. code-block:: bash

   python -m tests.fuzzing --interactive

Overnight run:

.. code-block:: bash

   python -m tests.fuzzing --forever --overall-timeout 0 --per-solver-timeout 20 --interactive --out-dir tests/_fuzzing_overnight

Interactive dashboard includes:

* solver matrix ``solver x PASS|SKIP|ERR|CRASH|TIMEOUT``
* fault totals
* top error-trigger feature tags
* top skip reasons
* progress indicators: ``iter_progress``, ``solver_progress``, and ``phase``

Notes:

* ``OpenWBOInc`` is excluded from the default fuzzing solver set.
* ``OpenWBO-PartMSU3`` is treated as ``SKIP`` on weighted instances in fuzzing mode.

Randomized Real-Instance Testing
--------------------------------

Run random testing over real ``.wcnf`` instances:

.. code-block:: bash

   python -m tests.randomized --data-dir tests/data --iterations 200

Indefinite run:

.. code-block:: bash

   python -m tests.randomized --data-dir tests/data --forever --interactive

Default artifacts are written under ``tests/_random/``.

See ``tests/README.md`` and ``tests/fuzzing/README.md`` for implementation
details and policy guidance.

References
----------

.. [1] Tobias Paxian, Armin Biere. *MaxSAT Fuzzing and Delta Debugging*. Journal of Artificial Intelligence Research, 85, 2026.
