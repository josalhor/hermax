Encoder Examples
================

The encoder layer accepts DIMACS literals and returns a ``CNFPlus`` object.
Its ``clauses`` can be appended to a SAT solver, while ``nv`` is the highest
variable identifier after auxiliary variables are allocated. Pass ``top_id``
when adding an encoding to an existing formula so its auxiliary variables do
not collide with existing identifiers.

Automatic Dispatch
------------------

Use :class:`hermax.encoder.PBCompiler` for a batch of mixed cardinality and
weighted PB constraints. It selects a cardinality encoder, PBLib, or the
structured PB(AMO) path for each item based on its coefficients and the AMO/EO
groups supplied with the batch.

.. literalinclude:: ../examples/encoder/00_auto.py
   :language: python
   :caption: examples/encoder/00_auto.py

Output
^^^^^^

.. literalinclude:: _generated/example_outputs/00_auto.txt
   :language: text
   :caption: Automatically dispatched batch

Cardinality
-----------

Use :class:`hermax.encoder.CardEnc` for unit-weight constraints. The methods
``atmost``, ``atleast``, and ``equals`` compile cardinality constraints.

.. literalinclude:: ../examples/encoder/01_cardinality.py
   :language: python
   :caption: examples/encoder/01_cardinality.py

Output
^^^^^^

.. literalinclude:: _generated/example_outputs/01_cardinality.txt
   :language: text
   :caption: Cardinality encoding and SAT checks

Pseudo-Boolean
--------------

Use :class:`hermax.encoder.PBEnc` when coefficients are not all one. Its
``leq``/``atmost``, ``geq``/``atleast``, and ``equals`` methods compile the
corresponding weighted constraint. ``PBEncType`` selects a backend encoding;
``best`` lets PBLib choose.

.. literalinclude:: ../examples/encoder/02_pseudo_boolean.py
   :language: python
   :caption: examples/encoder/02_pseudo_boolean.py

Output
^^^^^^

.. literalinclude:: _generated/example_outputs/02_pseudo_boolean.txt
   :language: text
   :caption: Pseudo-Boolean encoding and SAT checks

PB With AMO Structure
---------------------

Use :class:`hermax.encoder.PBAMOEnc` when the weighted literals are also
partitioned into known at-most-one groups. ``leq`` takes a disjoint partition;
``auto_leq`` accepts overlapping AMO/EO candidates and decides whether to use
a flat or structured encoding. Set ``emit_amo=True`` when the returned CNF
must include the AMO clauses as well.

.. literalinclude:: ../examples/encoder/03_pbamo.py
   :language: python
   :caption: examples/encoder/03_pbamo.py

Output
^^^^^^

.. literalinclude:: _generated/example_outputs/03_pbamo.txt
   :language: text
   :caption: Structured PB(AMO) encoding and SAT checks
