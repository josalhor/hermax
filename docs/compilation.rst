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

When in doubt, prefer this method over local builds.

See ``pyproject.toml`` and ``setup.py`` for up-to-date build
requirements

Installing
----------------------

The most reliable method is building wheels and testing with cibuildwheel:

.. code-block:: bash

    python -m cibuildwheel --output-dir wheelhouse
    pip install --force-reinstall wheelhouse/*.whl


Optional CPLEX-backed MaxHS / iMaxHS
------------------------------------

MaxHS and iMaxHS are optional and controlled by build environment variables.

Default behavior is auto-detect:

* if CPLEX headers + libraries are found, extensions are built
* otherwise they are skipped

Relevant variables:

* ``CPLEX_INC_DIR``
* ``CPLEX_LIB_DIR``
* ``HERMAX_ENABLE_MAXHS`` (``auto`` | ``on`` | ``off``)
* ``HERMAX_ENABLE_IMAXHS`` (``auto`` | ``on`` | ``off``)

Optional OptiLog Formula Support
--------------------------------

Hermax can optionally accept OptiLog ``WCNF`` formulas by converting them to
PySAT ``WCNF`` internally.

.. code-block:: bash

    pip install optilog==0.6.1

This dependency is optional because OptiLog has a separate proprietary
licensing model.