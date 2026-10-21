Conditionals and Implications
=======================================

* ``g.only_if(b)``: if ``b`` is true, enforce ``g``.
* ``g.implies(b)``: if ``g`` holds, ``b`` must be true.
* ``g.iff(b)``: ``b`` is true exactly when ``g`` holds.

Conditional Enforcement: ``only_if()``
----------------------------------------

``only_if(lit)`` means "enforce this constraint only when ``lit`` is true".

.. code-block:: python

   # If g is true, enforce (a OR b)
   gated_clause = (a | b).only_if(g)

   # If g is true, enforce a PB inequality
   gated_pb = (2 * a + b <= 2).only_if(g)

Multiple conditions can be chained:

.. code-block:: python

   chained = (a | b).only_if(g1).only_if(g2)
   # Meaning: (g1 AND g2) -> (a OR b)

Implication: ``implies()``
--------------------------

``src.implies(b)`` means "if ``src`` holds, ``b`` must be true".
The target must be a Boolean literal.

Examples include ``a.implies(b)``, ``(a | b).implies(c)``, and
``(x <= y).implies(b)``. It also works with weighted sums such as
``2 * a + b <= 2``, ``all_different()``, and ``table()``.

Equivalence: ``iff()``
----------------------

``constraint.iff(b)`` means that ``b`` is true exactly when the constraint holds.
Use it with literals, clauses, PB comparisons, integer comparisons such as
``x <= y`` or ``x == y``, and globals such as ``all_different()`` and
``table()``/``is_in()``.

.. code-block:: python

   x = model.int_vector("x", length=3, lb=0, ub=4)
   b = model.bool("b")
   g = x.all_different()

   model &= g.iff(b)                  # b <-> AllDifferent(x)
   # Equivalently: model &= b == g

   t = model.table(x, allowed=[(0, 1, 2), (2, 1, 0)])
   model &= t.iff(b)

   a, c = model.bool("a"), model.bool("c")
   model &= (a | c).iff(b)
   model &= (2 * a + c <= 2).iff(b)

Use ``~b`` as the indicator to reverse its meaning.
