Modelling
==============

The :mod:`hermax.model` module provides a pure-Python modelling DSL for MaxSAT
and SAT-like workflows, with eager evaluation.

The design goal is to let users model naturally while maintaining an efficient
path from high-level objects to exported ``CNF``/``WCNF``

Core Concepts
-------------

.. toctree::
   :maxdepth: 2

   modeling_overview
   modeling_boolean_pb
   modeling_modifiers
   modeling_typed
   modeling_collections

Solving And Export
------------------

.. toctree::
   :maxdepth: 2

   modeling_export_solve
   modeling_tricks

Examples
--------

See :doc:`examples` for runnable modelling examples and outputs.

API Reference
-------------

.. toctree::
   :maxdepth: 2

   modeling_api
