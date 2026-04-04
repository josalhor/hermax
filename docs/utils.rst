:orphan:

Utilities
=========

List of Functions
-----------------

.. autosummary::
   :nosignatures:

   hermax.core.utils.normalize_wcnf_formula

Module Description
------------------

Hermax supports PySAT WCNF formulas natively and can optionally accept
OptiLog WCNF formulas when OptiLog is installed [1]_ [2]_.

The function :func:`hermax.core.utils.normalize_wcnf_formula` provides the
central conversion path used by solver constructors:

* PySAT ``WCNF``/``WCNFPlus`` inputs are passed through unchanged
* OptiLog ``WCNF`` inputs are converted into PySAT ``WCNF``
* ``None`` is preserved.

This keeps solver wrappers simple and ensures consistent behavior across all
Hermax backends.

Optional OptiLog Compatibility
------------------------------

Install with OptiLog support using:

.. code-block:: bash

   pip install "hermax[optilog]"

OptiLog support is optional because OptiLog has **its own licensing model**.
PySAT remains a required dependency of Hermax.

Based on OptiLog's documented ``WCNF`` API (`hard_clauses` and
`soft_clauses`), Hermax converts:

* each item in ``hard_clauses`` into a hard clause in PySAT ``WCNF``
* each pair ``(weight, clause)`` in ``soft_clauses`` into a PySAT soft clause
  with that weight.

API Details
-----------

.. automodule:: hermax.core.utils
   :members:
   :undoc-members:

References
----------

.. [1] Carlos Ansótegui, Jesus Ojeda, António Pacheco, Josep Pon, Josep M. Salvia, Eduard Torres. *Optilog: A framework for SAT-based systems*. SAT 2021.
.. [2] Josep Alos, Carlos Ansótegui, Josep M. Salvia, Eduard Torres. *Optilog V2: model, solve, tune and run*. SAT 2022.
