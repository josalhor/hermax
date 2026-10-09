Encoding Layer API
==================

The ``hermax.encoder`` package compiles pseudo Boolean and cardinality
constraints to CNF.

Examples
--------

.. toctree::
   :maxdepth: 1

   encoder_examples

PBCompiler
----------

.. autoclass:: hermax.encoder.PBCompiler
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

PBItem
------

.. autoclass:: hermax.encoder.PBItem
   :members:
   :undoc-members:
   :show-inheritance:
   :member-order: bysource

References
-----------------------

Hermax uses the following encoder libraries and papers:

* PySAT (Cardinality): Hermax uses pycard from the PySAT toolkit.

  * *Reference*: Ignatiev, A., Morgado, A., & Marques-Silva, J. (2018). *PySAT: A Python Toolkit for Prototyping with SAT Oracles*.

* PBLib (Pseudo-Boolean): Hermax uses PBLib for PB encodings.

  * *Reference*: Manthey, N., Philipp, T., & Steinke, P. (2015). *PBLib - A Library for Encoding Pseudo-Boolean Constraints into CNF*.

* PB(AMO) (PB + AMO): Hermax uses PB(AMO) encodings in the modelling layer.
   
  * *Reference*: Bofill, M., Garcia, J., Suy, J., & Villaret, M. (2021). *SAT Encodings for Pseudo-Boolean Constraints Together With At-Most-One Constraints*.
