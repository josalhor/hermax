Modelling
==============

The :mod:`hermax.model` module provides Python modelling for MaxSAT
and SAT-like workflows.

The design goal is to let users model naturally while maintaining an efficient
path from high-level objects to exported ``CNF``/``WCNF``
and incremental solver calls.

Examples
--------

Start here if you want runnable modelling examples and outputs:

.. toctree::
   :maxdepth: 1

   model_examples
   model_examples_tricks
   np_problems

Core Concepts
-------------

.. toctree::
   :maxdepth: 2

   modeling_overview
   modeling_internal_overview
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

API Reference
-------------

.. toctree::
   :maxdepth: 2

   modeling_api
