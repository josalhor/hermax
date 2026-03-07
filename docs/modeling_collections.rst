Vectors, Matrices and Dicts
=========================================

The modelling layer provides structured containers for typed variables:

* vectors
* matrices
* keyed dictionaries

These containers keep models readable and easy to decode.

Vectors
-------

Constructors:

* ``model.bool_vector(name, length)``
* ``model.int_vector(name, length, lb, ub)``
* ``model.enum_vector(name, length, choices, nullable=False)``

Vectors support indexing, iteration, and typed helpers.

BoolVector helpers
------------------

``BoolVector`` provides cardinality helpers:

* ``at_most_one()``
* ``exactly_one()``
* ``at_least_one()``

Example:

.. code-block:: python

   row = model.bool_vector("row", 4)
   model &= row.exactly_one()

IntVector helpers
-----------------

``IntVector`` provides higher-level finite-domain constraints:

* ``all_different(backend=\"auto\")``
* ``increasing()`` (nondecreasing)
* ``lexicographic_less_than(other)``
* ``max(name=None)``
* ``min(name=None)``
* ``upper_bound(name=None)``
* ``lower_bound(name=None)``
* ``running_max(name=None)``
* ``running_min(name=None)``

Variable index: ``vec[idx]``
-------------------------------------------

``IntVector`` supports element constraints with a variable index:

.. code-block:: python

   vals = model.int_vector("vals", length=3, lb=0, ub=10)
   idx = model.int("idx", 0, 3)
   a = model.int("a", 0, 10)

   model &= (vals[idx] == a)

This compiles as conditional branch constraints:

.. math::

   (idx = i) \Rightarrow (vals_i \; OP \; rhs)

for each index value ``i`` and comparator ``OP``.

Supported comparators on ``vals[idx]``:

* ``==``, ``!=``
* ``<=``, ``<``, ``>=``, ``>``

RHS currently supports:

* integer constants
* ``IntVar``

Index coverage rules:

* ``idx.lb`` must be non-negative
* vector length must cover the index domain span ``[idx.lb, idx.ub)``

Constraint helpers (``all_different``, ``increasing``,
``lexicographic_less_than``) return :class:`ClauseGroup`.

The aggregate helpers:

* ``max(name=None)``
* ``min(name=None)``
* ``upper_bound(name=None)``
* ``lower_bound(name=None)``
* ``running_max(name=None)``
* ``running_min(name=None)``

return **lazy derived integer expressions**. They do not change the model.

Use :class:`~hermax.model.Model` methods for explicit eager materialization:

* ``model.max(vec_or_items, name=None)``
* ``model.min(vec_or_items, name=None)``
* ``model.upper_bound(vec_or_items, name=None)``
* ``model.lower_bound(vec_or_items, name=None)``

These methods also accept plain ``list``/``tuple`` of ``IntVar``.

Running Prefix
--------------

``IntVector.running_max()`` and ``IntVector.running_min()`` return **materialized**
prefix aggregates:

.. math::

   \begin{aligned}
   r_i^{\max} &= \max(x_0, \dots, x_i) \\
   r_i^{\min} &= \min(x_0, \dots, x_i)
   \end{aligned}

These helpers avoid rebuilding ``max(self[:i+1])`` / ``min(self[:i+1])`` at
each prefix (``O(N^2)`` clauses). They use a cumulative fold:

.. math::

   r_i^{\max} = \max(r_{i-1}^{\max}, x_i), \qquad
   r_i^{\min} = \min(r_{i-1}^{\min}, x_i)

Each step uses ``model.max(...)`` / ``model.min(...)``.

Example:

.. code-block:: python

   timeline = model.int_vector("level", 5, lb=0, ub=100)
   watermark = timeline.running_max("watermark")
   valley = timeline.running_min("valley")

   model &= (watermark[3] <= 50)
   model &= (valley[4] >= 10)

``IntVector.all_different()`` backends
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``IntVector.all_different()`` accepts a backend selector:

* ``backend=\"auto\"`` (default): currently aliases to ``\"pairwise\"``
* ``backend=\"pairwise\"``: pairwise ``x_i != x_j`` constraints
* ``backend=\"bipartite\"``: exact-value channeling + column at-most-one constraints

The ``bipartite`` backend currently requires:

* a common domain across the vector
* domain size at least the vector length

Min/Max Aggregates
---------------------------------

``IntVector.max()`` / ``IntVector.min()`` are lazy wrappers. The actual ladder
encoding is built by ``model.max(...)`` / ``model.min(...)`` when the aggregate
is materialized (for example in ``model &= ...`` or in a PB
constraint during Stage 2 compilation).

If ``t_k`` denotes the threshold predicate ``(x >= k)``, then:

.. math::

   \begin{aligned}
   z = \max(x_1,\dots,x_n) &\iff z_{\ge k} \leftrightarrow \bigvee_{i=1}^n x_{i,\ge k} \\
   z = \min(x_1,\dots,x_n) &\iff z_{\ge k} \leftrightarrow \bigwedge_{i=1}^n x_{i,\ge k}
   \end{aligned}

Example:

.. code-block:: python

   xs = model.int_vector("x", 4, lb=0, ub=10)
   xmax = xs.max("xmax")        # lazy derived int expression
   xmin = xs.min("xmin")        # lazy derived int expression
   model &= (xmin >= 2)
   model &= (xmax <= 7)

   xmax2 = model.max(xs, name="xmax2")
   xmin2 = model.min(xs, name="xmin2")

The output domain is inferred from the operands:

* ``max`` uses ``[max(lb_i), max(ub_i))``
* ``min`` uses ``[min(lb_i), min(ub_i))``

One-Sided Bounds
----------------

``IntVector.upper_bound()`` / ``IntVector.lower_bound()`` are lazy wrappers.
The eager implementations are ``model.upper_bound(...)`` and
``model.lower_bound(...)``, which build a fresh integer variable with only one
direction of the aggregate relation:

.. math::

   \begin{aligned}
   u = \mathrm{upper\_bound}(x_1,\dots,x_n) &\Rightarrow u \ge x_i \quad \forall i \\
   \ell = \mathrm{lower\_bound}(x_1,\dots,x_n) &\Rightarrow \ell \le x_i \quad \forall i
   \end{aligned}

These are weaker than exact ``max``/``min`` but cheaper: one direction only.

Example:

.. code-block:: python

   xs = model.int_vector("x", 4, lb=0, ub=10)
   ubv = model.upper_bound(xs, name="ubv")
   model.obj[1] += ubv

EnumVector helpers
------------------

``EnumVector.all_different(backend=\"auto\")`` is supported and returns a
:class:`ClauseGroup`.

Backends:

* ``backend=\"auto\"`` (default): aliases to ``\"bipartite\"``
* ``backend=\"bipartite\"``: column-wise at-most-one over enum choice literals
* ``backend=\"pairwise\"``: pairwise enum inequality constraints

For nullable enums, the current ``bipartite`` implementation falls back to the
pairwise backend so that the ``None`` case is handled correctly without adding a
dedicated ``is_none`` indicator literal.

Allowed combinations: ``Vector.is_in(rows)``
---------------------------------------------------

Typed vector views support allowed-combinations constraints:

* ``BoolVector.is_in(rows)``
* ``EnumVector.is_in(rows)``
* ``IntVector.is_in(rows)``

This is the model-layer table constraint:

.. code-block:: python

   cpu = model.int("cpu", 0, 6)
   ram = model.int("ram", 0, 6)
   mobo = model.int("mobo", 0, 6)

   spec = model.vector([cpu, ram, mobo])
   model &= spec.is_in([
       (1, 2, 1),
       (2, 4, 2),
       (3, 4, 3),
   ])


Arbitrary typed vector views
----------------------------

Use ``model.vector(items)`` to build a typed vector view from an arbitrary
subset of variables:

.. code-block:: python

   region = model.vector([grid[r, c] for r in rows for c in cols])
   model &= region.all_different()

This is useful for irregular subsets such as Sudoku subgrids, selected
resources, or custom neighborhoods, and for combining subset views with
``.is_in(rows)``.

Matrices
--------

Constructors:

* ``model.bool_matrix(name, rows, cols)``
* ``model.int_matrix(name, rows, cols, lb, ub)``
* ``model.enum_matrix(name, rows, cols, choices, nullable=False)``

Matrix helpers
--------------

All matrix types support:

* ``row(i)``
* ``col(j)``
* ``flatten()``

and also **NumPy indexing**:

* ``m[r, c]`` -> cell
* ``m[r, :]`` -> typed row vector
* ``m[:, c]`` -> typed column vector
* ``m[r0:r1, c0:c1]`` -> typed submatrix view
* ``m[r0:r1, c0:c1].flatten()`` -> typed vector

Example (Sudoku subgrid)
------------------------

.. code-block:: python

   grid = model.int_matrix("cell", 9, 9, lb=1, ub=10)
   model &= grid[0:3, 0:3].flatten().all_different()

This is the intended NumPy-style syntax for rectangular subsets.

Keyed Dictionaries
------------------

Constructors:

* ``model.bool_dict(name, keys)``
* ``model.int_dict(name, keys, lb, ub)``
* ``model.enum_dict(name, keys, choices, nullable=False)``

These are useful when natural indexing is not numeric.

Example: 

.. code-block:: python

   routers = [10, 20, 30]
   state = model.enum_dict("router_state", routers, choices=["1", "2", "3"], nullable=True)
   model &= ~(state[10] == "1") | ~(state[20] == "1")

This pattern is used in ``examples/wifi_model.py``. Combined with
``EnumVar.is_in(...)`` it gives a compact API for category subsets.

Decode Support
--------------

Model solution auto-decodes containers directly:

* vector -> Python list
* matrix / matrix view -> nested list
* dict -> Python dict keyed by original keys

Example:

.. literalinclude:: ../examples/model/21_decode_collections.py
   :language: python
   :caption: examples/model/21_decode_collections.py

Example output
^^^^^^^^^^^^^^

.. literalinclude:: _generated/example_outputs/21_decode_collections.txt
   :language: console
