Encoding Layer API
==================

The ``hermax.encoder`` package provides a unified way for compiling 
Pseudo-Boolean and Cardinality constraints efficiently.

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

The encoders used in Hermax are state-of-the-art research 
in SAT encoding techniques. References:

* PySAT (Cardinality): Hermax uses pycard from the PySAT toolkit.

  * *Reference*: Ignatiev, A., Morgado, A., & Marques-Silva, J. (2018). *PySAT: A Python Toolkit for Prototyping with SAT Oracles*.

* PBLib (Pseudo-Boolean): We use the PBLib library for our PB encoding strategies.

  * *Reference*: Manthey, N., Philipp, T., & Steinke, P. (2015). *PBLib - A Library for Encoding Pseudo-Boolean Constraints into CNF*.

* PB(AMO) (PB + AMO): We provide bindings to PB(AMO) encodings, which we exploit in our modelling layer.
   
  * *Reference*: Bofill, M., Garcia, J., Suy, J., & Villaret, M. (2021). *SAT Encodings for Pseudo-Boolean Constraints Together With At-Most-One Constraints*.
