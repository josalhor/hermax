Enum and Int
=============================

Typed finite-domain variables on top of Boolean literals:

* :class:`hermax.model.EnumVar`
* :class:`hermax.model.IntVar`

They emit domain constraints and decode back to typed values.

Enum Variables
--------------

Create an enum:

.. code-block:: python

   color = model.enum("color", choices=["red", "green", "blue"])

Enum variables expose equality to a choice label:

.. code-block:: python

   model &= (color == "red")

Enum subset membership
----------------------

``EnumVar.is_in(...)`` is a fast CNF helper for common subset-membership tests:

.. code-block:: python

   model &= shift_type.is_in(["morning", "day"])

This returns a flat :class:`Clause` over the underlying choice literals
without introducing auxiliary variables.

* Non-nullable enum -> Exactly one choice must be selected
* Nullable enum -> At most one choice, with ``None`` meaning "no choice"

Nullable enums are useful for "optional assignment" modelling.

Enum-to-Enum Relations
----------------------

Enum variables support:

* ``enum1 == enum2`` (returns :class:`ClauseGroup`)
* ``enum1 != enum2`` (returns :class:`ClauseGroup`)

The choices must match.

Integer Variables
-----------------------------------

Create a bounded integer in range ``[lb, ub)``:

.. code-block:: python

   x = model.int("x", lb=0, ub=10)

``IntVar`` uses a **ladder / order encoding** internally. This is part of the
model contract.

Examples:

* ``lb=0, ub=10`` -> values ``0..9``
* ``lb=3, ub=7`` -> values ``3..6``

.. code-block:: python

   x = model.int("x", lb=3, ub=9)
   assert x.lower_bound() == 3
   assert x.upper_bound() == 8

These return declared bounds. ``upper_bound()`` returns ``ub - 1``.

Bounded Int comparisons
-----------------------------------

Scalar comparisons return Boolean literals:

.. code-block:: python

   model &= (x <= 4)
   model &= (x > 1)
   model &= (x == 3)

These literals are exact and tied to the ladder encoding.

The model implements exact integer relations across int variables:

* ``x == y``
* ``x != y``
* ``x <= y``
* ``x < y``
* ``x >= y``
* ``x > y``

which return :class:`ClauseGroup`.

Full Boolean reification of Int relations
-----------------------------------------

Boolean indicators can be tied to native integer relations directly:

.. code-block:: python

   b = model.bool("b")
   model &= (b == (x <= y))

This encodes full equivalence:

.. math::

   b \leftrightarrow (x \le y)

Similarly for ``<``, ``>=``, and ``>``.
Equality is also supported:

.. code-block:: python

   model &= (b == (x == y))

This uses ladder relation clauses in both directions, with
no PB/Card encoder dispatch being used for this reification shape.

Performance notes
-----------------

These relations are implemented to respect the ladder encoding:

* ``x == y`` is linear in the domain cut span
* ``x <= y`` / ``x >= y`` are linear in the domain cut span
* ``x != y`` is linear in overlap size and introduces no new variables

This avoids naive quadratic approaches.

Ladder constraints
-------------------------

The ladder encoding enables constraints that compile to small CNF directly,
without PB/cardinality encoders.

Distance bound: ``|x - y| <= D``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use :meth:`hermax.model.IntVar.distance_at_most`:

.. code-block:: python

   model &= x.distance_at_most(y, 3)

This compiles to ladder-threshold implications and introduces no auxiliary
variables. It is linear in the relevant threshold cuts and mostly binary clauses.

Edge cases:

* ``D = 0`` behaves like equality (``x == y``)
* ``D < 0`` raises ``ValueError``

Skipping values in domains: ``forbid_value()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use :meth:`hermax.model.IntVar.forbid_value` to remove a single value from a
domain:

.. code-block:: python

   for v in [4, 7, 9]:
       model &= x.forbid_value(v)

This exploits the ladder "cliff" pattern for an exact value and compiles to a
tiny clause, where:

* Interior values usually produce a binary clause
* Boundary values often collapse to a unit clause
* Values outside the declared domain return a tautological no-op clause

Skipping large value ranges: ``forbid_interval()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use :meth:`hermax.model.IntVar.forbid_interval` to remove an entire closed
interval from the domain:

.. code-block:: python

   model &= x.forbid_interval(200, 800)

This uses the ladder jump implication:

.. math::

   x \ge \text{start} \;\Rightarrow\; x \ge \text{end}+1

and compiles to a single small clause after domain clipping.

Use this instead of many ``forbid_value()`` calls for large gaps.

Range membership indicator: ``in_range()``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use :meth:`hermax.model.IntVar.in_range` to build a reusable Boolean literal
representing inclusive range membership:

.. code-block:: python

   afternoon = task_end.in_range(13, 17)
   model &= afternoon

The returned object is a :class:`~hermax.model.Literal`, so it composes with
PB/cardinality constraints (for example, histogram/binning counts):

.. code-block:: python

   bins = [t.in_range(0, 12) for t in end_times]
   model &= (sum(bins) <= 10)

``x.in_range(start, end)`` represents:

.. math::

   \text{start} \le x \le \text{end}

Internally, this is the ladder predicate:

.. math::

   (x \ge \text{start}) \land (x < \text{end}+1)

and the returned indicator literal is defined lazily (via deferred helper
clauses), so constructing it does not immediately mutate the model.


Using ``IntVar`` in PB expressions
----------------------------------

``IntVar`` can be lifted into PB expressions:

.. code-block:: python

   model &= (a + x <= 7)
   model &= (a + 2 * x <= 7)
   model &= (a - x <= 0)


Piecewise Step Functions as PB
-----------------------------------------------

``IntVar`` can also be mapped to a step function directly as a lazy
:class:`~hermax.model.PBExpr`:

.. code-block:: python

   cost = x.piecewise(
       base_value=10,
       steps={
           10: 25,
           50: 100,
       },
   )
   model &= (cost <= budget)


``steps`` is a mapping ``{threshold: new_value}`` interpreted in sorted
threshold order. For every threshold ``t``:

* If ``x >= t``, the piecewise value becomes ``steps[t]``
* Otherwise, the previous value remains active

Formally, for a sorted threshold sequence ``t_1 < t_2 < \dots < t_m`` and
piecewise values ``v_0`` (the base value), ``v_1, \dots, v_m``, the returned
expression is represented as:

.. math::

   f(x) = v_0 + \sum_{i=1}^{m} (v_i - v_{i-1}) \cdot [x \ge t_i]

where ``[x >= t_i]`` is the ladder-threshold literal for the integer variable.

This construction:

* Burns no new variables
* Emits no clauses at construction time
* Reuses the existing ladder literals of ``x``
* Composes into later PB constraints

The result is just a :class:`~hermax.model.PBExpr`.

Non-monotonic step functions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The function values do not need to be monotone. If a later step decreases the
value, the corresponding delta is negative and is handled by the existing PB
normalization pipeline when the expression is compiled [1]_.

For example:

.. code-block:: python

   # 50 -> 80 at x>=2, then back down to 30 at x>=4
   penalty = x.piecewise(base_value=50, steps={2: 80, 4: 30})

Boundary handling
^^^^^^^^^^^^^^^^^

Thresholds are clipped against the integer domain:

* thresholds ``<= lb`` are folded into the effective base value
* thresholds ``>= ub`` are ignored (never active)
* zero-delta steps are elided

``IntVar`` in objective
-----------------------

You can add an integer variable directly to the weighted objective:

.. code-block:: python

   x = model.int("x", lb=0, ub=10)
   model.obj[3] += x

This lowers to ``O(n)`` soft clauses using ladder bits (one weighted soft unit
per threshold bit) and is equivalent to minimizing the integer value.

``obj[w] += int_var`` requires ``int_var.lb >= 0``.

``IntVar`` scaling (multiplication)
------------------------------------

The model also provides an eager way to scale an integer by a positive constant
into a new integer variable:

.. code-block:: python

   y = model.scale(x, 3)
   model &= (y <= 12)

This uses direct ladder-threshold ties (no PB/Card encoder).

``x * 3`` remains the algebraic/PB syntax and produces a :class:`PBExpr`. The
compiler may still optimize PB comparisons containing scaled integers (for
example ``2*x + 3*y <= 17``) using internal ladder fast paths.

Constant division via ``//``
------------------------------------------

``IntVar`` supports floor division by a **positive integer constant**:

.. code-block:: python

   q = x // 10
   model &= (q <= 3)

``x // d`` returns a **lazy derived integer expression** (``DivExpr``). It does
not mutate the model immediately.

If you want the explicit eager API, use:

.. code-block:: python

   q = model.floor_div(x, 10)

Both forms are equivalent. The lazy form is realized automatically when used in
``model &= ...``, ``model.obj[...] +=``, or inside a PB expression compiled in
Stage 2.

Why this is fast
^^^^^^^^^^^^^^^^

For positive ``d``, if ``q = x // d``, then for every quotient threshold ``m``:

.. math::

   q_{\ge m} \;\leftrightarrow\; x_{\ge m \cdot d}

The model compiles constant division using direct threshold
equivalences, without PB/cardinality encoders.
Divisors must be strictly positive integers.

Lazy array indexing via ``@``
-----------------------------

``IntVar`` also supports lazy array-indexing for arrays of integer constants:

.. code-block:: python

   costs = [10, 100, 1000]
   w = model.int("w", lb=0, ub=3)
   model &= (costs @ w <= 50)

The expression ``costs @ w`` creates a lazy descriptor. On comparison, the
model unrolls the index domain and compiles a flat :class:`ClauseGroup`.

Supported forms:

* integer constant
* another ``IntVar``

Variable index on ``IntVector``
---------------------------------------------------

``IntVector`` also supports variable indexing directly:

.. code-block:: python

   vals = model.int_vector("vals", length=3, lb=0, ub=10)
   idx = model.int("idx", 0, 3)
   a = model.int("a", 0, 10)
   model &= (vals[idx] == a)

Equivalence rule:

.. math::

   (idx = i) \Rightarrow (vals_i \; OP \; rhs)

for ``OP`` in ``==, !=, <=, <, >=, >``.

Current constraints:

* ``idx.lb >= 0``
* vector length covers ``[idx.lb, idx.ub)``

For canonical element equality/ordering shapes, this compiles to flat conditional
clauses and avoids generic PB/Card dispatch.

Intervals
---------

The modelling layer also provides a lightweight scheduling object:

* :class:`hermax.model.IntervalVar`

Create intervals with a fixed duration and a bounded horizon:

.. code-block:: python

   task_a = model.interval("A", start=0, duration=5, end=24)
   task_b = model.interval("B", start=0, duration=3, end=24)

   model &= task_a.ends_before(task_b)
   model &= task_a.no_overlap(task_b)

The interval constructor uses:

* ``start`` = earliest start time (inclusive)
* ``end`` = latest end time (inclusive)
* ``duration`` = positive fixed duration

Internally, an interval owns two :class:`hermax.model.IntVar` objects:

* ``interval.start``
* ``interval.end``

and the model enforces:

* ``interval.end == interval.start + duration``

Methods
^^^^^^^

Currently implemented:

* ``ends_before(other)``  -> enforces ``self.end <= other.start``
* ``starts_after(other)`` -> enforces ``self.start >= other.end``
* ``no_overlap(other)``   -> disjunctive non-overlap (either orientation)

``no_overlap`` allows touching intervals (i.e. ``end == other.start`` is valid).

Performance
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The interval identity ``end == start + duration`` is **not** compiled through
the generic PB/Cardinality encoder pipeline.

Instead, because both endpoints use the same ladder width by construction, the
model directly welds the endpoint ladders with threshold-bit equivalences:

* ``start_t[i] <-> end_t[i]`` for each ladder position ``i``

This yields:

* **O(n)** binary clauses (where ``n`` is the ladder width)
* **zero auxiliary variables**

References
----------

.. [1] Niklas Eén and Niklas Sörensson. "Translating pseudo-boolean
   constraints into SAT." *Journal on Satisfiability, Boolean Modelling and
   Computation*, 2(1-4):1-26, 2006.
