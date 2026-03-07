Compilation
===========

Recommended Workflow
--------------------

For contributors, the source of truth for build dependencies:

* ``pyproject.toml``
* ``setup.py``

The recommended approach is:

1. Install system/native libraries required by those files on your platform.
2. Build wheels with ``cibuildwheel``.
3. Install and test the produced wheel locally.

When in doubt, prefer this wheel-first workflow over ad-hoc local builds.

See ``pyproject.toml`` and ``setup.py`` for up-to-date build
requirements

Installing
----------------------


The most reliable developer workflow is building wheels and testing that exact
artifact:

.. code-block:: bash

    python -m cibuildwheel --output-dir wheelhouse
    pip install --force-reinstall wheelhouse/*.whl

Alternatively, for a more iterative workflow, you can install from the source:

.. code-block:: bash

    pip install .

This will trigger the CMake build process for all the bundled solvers.

Optional OptiLog Formula Support
--------------------------------

Hermax can optionally accept OptiLog ``WCNF`` formulas by converting them to
PySAT ``WCNF`` internally.

For source-based workflows, install OptiLog directly:

.. code-block:: bash

    pip install optilog==0.6.1

This dependency is optional because OptiLog has a separate proprietary
licensing model.

CIBuildWheel
------------

`hermax` uses `cibuildwheel` for generating multi-platform wheels. The configuration is stored in `pyproject.toml`.
