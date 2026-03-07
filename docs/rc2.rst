:orphan:

RC2 Family
==========

List of Classes
---------------

.. autosummary::
   :nosignatures:

   hermax.non_incremental.RC2

Module Description
------------------

Hermax provides one public RC2-facing API:

* :class:`hermax.non_incremental.RC2`:
  non-incremental/re-encoding wrapper [1]_ [2]_.

It preserves the common :class:`hermax.core.ipamir_solver_interface.IPAMIRSolver`
interface.

API Details
-----------

Detailed method-level API for RC2 classes is documented in
:doc:`non_incremental`.

References
----------

.. [1] Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva. *RC2: An Efficient MaxSAT Solver*. JSAT 11(1), 2019.
.. [2] Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva. *PySAT: A Python Toolkit for Prototyping with SAT Oracles*. SAT 2018.
