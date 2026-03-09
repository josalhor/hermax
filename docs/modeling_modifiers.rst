Conditionals and Implications
=======================================

The modelling layer supports two important modifier-style operations:

* ``.only_if(literal)``
* ``.implies(target)``

Conditional Enforcement: ``only_if()``
----------------------------------------

``only_if(lit)`` means "enforce this constraint only when ``lit`` is true".

Supported on:

* :class:`hermax.model.Literal`
* :class:`hermax.model.Clause`
* :class:`hermax.model.ClauseGroup`
* :class:`hermax.model.PBConstraint`

Examples:

.. code-block:: python

   # If g is true, enforce (a OR b)
   gated_clause = (a | b).only_if(g)

   # If g is true, enforce a PB inequality
   gated_pb = (2 * a + b <= 2).only_if(g)

Chaining gates is supported and remains sound:

.. code-block:: python

   chained = (a | b).only_if(g1).only_if(g2)
   # Meaning: (g1 AND g2) -> (a OR b)

Implication: ``implies()``
--------------------------

``src.implies(dst)`` is implemented as a safe form of half-reification.

Supported source forms
----------------------

* :class:`hermax.model.Literal`
* :class:`hermax.model.Clause`
* :class:`hermax.model.PBConstraint`

Unsupported source forms
------------------------

* :class:`hermax.model.ClauseGroup`
