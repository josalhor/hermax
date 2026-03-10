Boolean and PB Modelling
========================

Core modelling objects for Boolean clauses and pseudo-Boolean (PB) constraints.

Boolean Building Blocks
-----------------------

The basic Boolean layer is:

* :class:`hermax.model.Literal`
* :class:`hermax.model.Clause`
* :class:`hermax.model.ClauseGroup`

Typical usage:

.. code-block:: python

   from hermax.model import Model

   m = Model()
   a = m.bool("a")
   b = m.bool("b")
   c = m.bool("c")

   # (a OR b)
   clause = a | b

   # (a) AND (b) AND (c) as CNF (three unit clauses)
   cnf_group = a & b & c

   # Mixed chaining remains CNF-shaped
   mixed = (a | b) & c

Notes
-----

* ``|`` builds a single clause (disjunction).
* ``&`` builds a clause group (conjunction of clauses).
* ``ClauseGroup`` is immutable by operator: ``x &= y`` returns a new group.
* ``Clause`` is immutable by operator: ``x |= y`` returns a new clause.
* Explicit mutation is available (with a guard), for example:

  * ``clause.append(lit, inplace=True)``
  * ``group.extend(x, inplace=True)``

PB Arithmetic
-------------

PB expressions are built from booleans (and also :class:`IntVar`, covered on
the typed page):

* :class:`hermax.model.Term`
* :class:`hermax.model.PBExpr`
* :class:`hermax.model.PBConstraint`

Examples:

.. code-block:: python

   expr = 3 * a + 2 * b - c
   pb = expr <= 4

   scaled = 2 * (a + b)      # PBExpr scalar multiplication
   pb2 = scaled <= 2

``pb`` is a lazy :class:`hermax.model.PBConstraint`, not yet a compiled CNF
object.

PB Expression
----------------

``PBExpr`` represents a weighted sum of literals.
The model layer normalizes these algebraically before encoding.

Examples:

.. code-block:: python

   ok = (a + b <= 1)       # valid
   ok = (3 * a - b >= 0)   # valid
   ok = (sum([a, b], 0) <= 1)  # valid (+0 no-op)

   ok = (a + b + 2 <= 3)  # equivalent to a + b <= 1

PB Compilation
-----------------------------

PB comparisons produce a lazy descriptor:

.. code-block:: python

   pb = (2 * a + b <= 2)

It compiles to CNF when:

* added to the model as a hard constraint (``model &= pb``)
* added as a soft constraint (``model.obj[w] += pb``)
* explicitly materialized (``pb.clauses()``)

``pb.clauses()`` returns a :class:`hermax.model.ClauseGroup` and caches the
compiled result.

PB as a Soft Constraint
---------------------------------

``model.obj[w] += pb_constraint`` is supported and uses targeted relaxation
internally:

* one weighted soft penalty literal
* plus the compiled PB network conditional as hard clauses

Encoder Dispatch
----------------

The model dispatches PB comparators automatically:

* all coefficients are the same -> cardinality encoding via ``pysat.card.CardEnc``
* otherwise -> weighted PB encoding via ``pysat.pb.PBEnc``

Fast Paths for PB Constraints
--------------------------------------------

Before falling back to generic PB/Card encoders, the compiler recognizes several
``IntVar`` patterns and emits ladder clauses instead (no
``PBEnc``/``CardEnc`` calls):

* offset precedence/equality: ``x + c <= y``, ``x - c == y``
* scaled relations: ``a*x <= y``, ``a*x + c == y``
* bivariate forms: ``a*x + b*y OP c`` for ``OP`` in
  ``<=, <, >=, >, ==``
* some trivariate sums: ``x + y <= z`` and ``x + y < z``
* exact bool-sum channeling to IntVar:
  ``x + c1 OP (b1 + ... + bn) + c2`` for
  ``OP in {==, <=, >=, <, >}`` (unit-weight boolean sums)

Examples:

.. code-block:: python

   model &= (x + 5 <= y)
   model &= (3 * x == y)
   model &= (2 * x + 3 * y <= 17)
   model &= (x + 1 == (a + b + c) - 2)
   model &= (x + 1 <= (a + b + c) - 2)
   model &= (x + 1 >= (a + b + c) - 2)

For these bool-sum shapes, the compiler uses a sequential counter and channels
its ``count>=k`` states to ladder thresholds of ``x``:

* ``==`` uses bidirectional channeling
* ``<=`` uses ``x>=k -> count>=k``
* ``>=`` uses ``count>=k -> x>=k``
* strict forms ``<`` and ``>`` are normalized to non-strict shifted forms

Unsupported shapes (for example, non-canonical 3+ integer forms or mixed
boolean terms) fall back to generic
PB/Card encoding.

Normalization
-------------

Before encoding, expressions are normalized:

* repeated literals are merged (e.g. ``a + b + 2*b -> a + 3*b``)
* coefficients are reduced by GCD when possible
* cancellations are collapsed (e.g. ``a + b - b -> a``)
* negative coefficients are normalized
* trivial bounds are short circuited

Explicit PBExpr mutation
------------------------

``PBExpr`` operators are immutable by contract, but explicit mutation is
available when needed:

.. code-block:: python

   expr = a + b
   expr.add(2 * a, inplace=True)
   expr.sub(b, inplace=True)

The ``inplace=True`` keyword is mandatory by design.
