PB(AMO) API
==================

Hermax includes an internal structured pseudo-Boolean layer for constraints
that can exploit known ``AMO``/``EO`` structure [1]_.

This is useful for constraints of the form:

.. code-block:: text

   sum(w_i * x_i) <= K

when some of the ``x_i`` are known to belong to at-most-one (AMO) or exactly-one (EO)
groups. Instead of flattening the whole constraint into an ordinary PB, the
structured layer can route it to encoders that treat those groups efficiently.

Current Status
--------------

The structured PB API is part of the :mod:`hermax.encoder` package:

.. code-block:: python

   from hermax.encoder import PBAMOEnc
   from hermax.encoder.pbamo import EncType, OverlapPolicy


Two entry points are available:

* ``PBAMOEnc.leq(...)`` for a disjoint AMO partition you already know
* ``PBAMOEnc.auto_leq(...)`` for overlapping ``AMO`` / ``EO``
  candidates, automatic overlap resolution, and automatic routing between flat
  ``CardEnc`` / ``PBEnc`` and structured encoders

Disjoint Partition API
----------------------

Use ``leq(...)`` when you already have a clean disjoint partition:

.. literalinclude:: ../examples/model/32_structuredpb_disjoint.py
   :language: python
   :caption: examples/model/32_structuredpb_disjoint.py

Output
^^^^^^

.. literalinclude:: _generated/example_outputs/32_structuredpb_disjoint.txt
   :language: text
   :caption: Structured PB with a disjoint AMO partition

Arguments:

* ``lits``: PB literals
* ``weights``: integer PB coefficients
* ``groups``: disjoint AMO partition over ``lits``
* ``bound``: right-hand side of ``sum(w_i * x_i) <= bound``
* ``encoding``: one of ``mdd``, ``gswc``, ``ggpw``, ``gmto``, ``rggt``, or
  ``best``
* ``emit_amo``: whether to also emit pairwise AMO clauses for the groups

Automatic Overlap API
---------------------

Use ``auto_leq(...)`` when you have overlapping candidates instead of a clean
partition, or when you want the internal router to decide whether a
unit-weight cardinality / pseudo-Boolean constraint should stay flat or move
to the structured side:

.. literalinclude:: ../examples/model/33_structuredpb_auto_overlap.py
   :language: python
   :caption: examples/model/33_structuredpb_auto_overlap.py

Output
^^^^^^

.. literalinclude:: _generated/example_outputs/33_structuredpb_auto_overlap.txt
   :language: text
   :caption: Structured PB with overlapping AMO and EO candidates

``auto_leq(...)`` does three things:

1. resolves overlapping ``AMO`` / ``EO`` candidates into one disjoint
   partition
2. decides whether the instance should stay in ordinary flat
   ``CardEnc`` / ``PBEnc`` or go to the structured encoders
3. if routed to the structured side, chooses the structured encoder

The original overlapping ``AMO`` / ``EO`` constraints are still emitted
explicitly as clauses, so the overlap resolution policy only decides which
partition is fed to the structured encoder.

Overlap Policy
--------------

Two overlap policies are available:

* ``baseline_paper``
* ``paper_best_fit_dynamic_future``

``baseline_paper`` is the direct paper-style greedy baseline [1]_:

* process literals in input order
* place each literal into the first compatible existing group
* otherwise start a new group

``paper_best_fit_dynamic_future`` is the current improved policy built on top
of that baseline:

* choose the next literal dynamically, prioritizing the hardest literals first
* among compatible groups, choose the best fit rather than the first fit
* prefer placements with:

  * stronger EO support
  * stronger AMO/EO overlap support
  * more future compatibility for remaining literals
  * larger reusable groups

The paper baseline basically says: "place literals in order and use the first group that works"; our policy says: "place the hardest literal next, and put it where it fits best without harming future placements"

References
----------

.. [1] Miquel Bofill, Jordi Coll, Peter Nightingale, Josep Suy,
   Felix Ulrich-Oltean, Mateu Villaret.
   *SAT encodings for Pseudo-Boolean constraints together with at-most-one
   constraints*. *Artificial Intelligence*, 302:103604, 2022.
