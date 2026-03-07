Advanced Modelling Examples
==========================================================

Conventions
-----------

* Hermax solves **minimization** problems.
* ``model.obj[w] += expr`` minimizes the numeric value of ``w * expr``.
* ``IntVar`` values are bounded over half-open domains ``[lb, ub)``.
* ``x >= k`` in the implementation corresponds to a ladder threshold literal.


Example 13: Piecewise
--------------------------------------

When to use this
^^^^^^^^^^^^^^^^

Use this pattern when a cost or penalty depends on an integer variable through
tiers, and you want to use that cost in both constraints and the objective.

Why this is efficient
^^^^^^^^^^^^^^^^^^^^^

The piecewise expression is compiled as a weighted sum over the existing ladder
literals of the integer variable. It does **not** create a proxy integer
variable for the mapped cost. In practice, this removes a large amount of
unnecessary encoding work in budget-style models.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.IntVar.piecewise`
* direct objective lowering of linear expressions (``model.obj[w] += expr``)

Model
^^^^^

The tariff is a step function of the load. The model constrains the tariff by
budget and then minimizes the combination of load and tariff.

.. math::

   \begin{aligned}
   \text{Variable:}\quad & load \in \{0,\dots,11\} \\
   \text{Tariff:}\quad &
      tariff(load)=
      \begin{cases}
      10 & 0 \le load < 4 \\
      25 & 4 \le load < 8 \\
      60 & 8 \le load < 12
      \end{cases} \\
   \text{Hard budget cap:}\quad & tariff(load) \le 25 \\
   \text{Objective:}\quad & \min \; load + tariff(load)
   \end{aligned}

Code
^^^^

.. literalinclude:: ../examples/model/13_piecewise_pricing_budget.py
   :language: python
   :caption: examples/model/13_piecewise_pricing_budget.py

Output
^^^^^^

The optimizer keeps the load in the cheapest pricing tier while satisfying the
budget cap.

.. literalinclude:: _generated/example_outputs/13_piecewise_pricing_budget.txt
   :language: console


Example 14: Histogram Binning
-----------------------------

When to use this
^^^^^^^^^^^^^^^^

Use this when you need counts over integer buckets and want those counts in constraints
or the objective.

Why this is efficient
^^^^^^^^^^^^^^^^^^^^^

``in_range()`` returns a reusable boolean indicator for an interval, which can be summed directly, whic is very efficient.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.IntVar.in_range`
* Decoding Python ``list``/``tuple`` collections from the solution object

Model
^^^^^

Each bin indicator represents inclusive interval membership, and histogram
constraints are plain sums of booleans.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & t_i \in \{0,\dots,23\} \\
   \text{Bins:}\quad &
      m_i = [0 \le t_i \le 11],\;
      a_i = [12 \le t_i \le 17],\;
      e_i = [18 \le t_i \le 23] \\
   \text{Histogram constraints:}\quad &
      \sum_i m_i = 3,\quad
      \sum_i a_i = 2,\quad
      \sum_i e_i = 1
   \end{aligned}

Code
^^^^

.. literalinclude:: ../examples/model/14_histogram_binning.py
   :language: python
   :caption: examples/model/14_histogram_binning.py

Output
^^^^^^

The decoded list output shows the chosen completion times, and the three bin
counts match the target histogram exactly.

.. literalinclude:: _generated/example_outputs/14_histogram_binning.txt
   :language: console


Example 15: Domain Holes + Distance Bound
-----------------------------------------

When to use this
^^^^^^^^^^^^^^^^

Use this when the domain itself carries structure and you want to encode
that structure directly instead of routing through generic pseudo-Boolean
constraints.

Why this is efficient
^^^^^^^^^^^^^^^^^^^^^

These constraints compile to very small clause sets and do not need PB/Card encoders. They are especially useful when the
domain is large but the forbidden structure is simple.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.IntVar.forbid_interval`
* :meth:`hermax.model.IntVar.forbid_value`
* :meth:`hermax.model.IntVar.distance_at_most`

Model
^^^^^

This model is domain-constraint heavy and uses ladder operations
throughout.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x,y \in \{0,\dots,29\} \\
   \text{Holes:}\quad & x \notin [10,20],\quad y \neq 13 \\
   \text{Proximity:}\quad & |x-y| \le 2 \\
   \text{Objective:}\quad & \min \; -score(x) - score(y)
   \end{aligned}

where ``score`` is expressed with ``piecewise(...)`` and lowered directly as a
step-cost expression in the objective.

Code
^^^^

.. literalinclude:: ../examples/model/15_domain_holes_and_distance.py
   :language: python
   :caption: examples/model/15_domain_holes_and_distance.py

Output
^^^^^^

The solver returns values that avoid the forbidden hole and satisfy the distance
bound without using generic PB/Card encoders for these constraints.

.. literalinclude:: _generated/example_outputs/15_domain_holes_and_distance.txt
   :language: console


Example 16: Lazy Division + Scaling
-------------------------------------------------------

When to use this
^^^^^^^^^^^^^^^^

Use this when your model has coarse units or derived quantities and you still want to write natural
algebraic constraints.

Why this is efficient
^^^^^^^^^^^^^^^^^^^^^

The syntax looks like generic arithmetic, but the compiler recognizes these
forms and compiles them with ladder fast paths instead of generic PB/Card
encoders. This can remove a large amount of auxiliary-variable bloat in
scheduling/resource models.

New primitives
^^^^^^^^^^^^^^

* ``x // d`` (lazy division expression)
* ``x.scale(c)`` (lazy scaling expression)
* Affine integer fast paths (transparent compiler optimization)

Model
^^^^^

The example combines quotient and scaled forms in ordinary algebraic syntax.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x \in [0,30),\ y \in [0,50) \\
   q &= \lfloor x/4 \rfloor \\
   s &= 3x \\
   \text{Hard constraints:}\quad & s + 2 \le y,\quad q = 3 \\
   \text{Objective:}\quad & \min y
   \end{aligned}

Code
^^^^

.. literalinclude:: ../examples/model/16_lazy_div_scale_affine.py
   :language: python
   :caption: examples/model/16_lazy_div_scale_affine.py

Output
^^^^^^

The printed quotient and scaled value make it easy to verify that the lazy
derived expressions are being used correctly in the affine constraints.

.. literalinclude:: _generated/example_outputs/16_lazy_div_scale_affine.txt
   :language: console


Example 17: Big-M Capacity Constraint
-------------------------------------

When to use this
^^^^^^^^^^^^^^^^

Use this for the classic Opertions Research (OR) pattern \[if boolean is on, integer bound shifts\].
This appears in optional resources, setup-dependent capacities, truck/worker
activation, and many Big-M formulations.

Why this is efficient
^^^^^^^^^^^^^^^^^^^^^

This pattern is compiled as a pair of conditional ladder bounds instead of a generic
PB encoding. In practice, that usually means fewer clauses and far fewer
auxiliary variables than a naive Big-M lowering.

New primitives
^^^^^^^^^^^^^^

No new user primitives are introduced; This example showcases a transparent compiler fast path.

Model
^^^^^

The user writes ordinary affine syntax. The boolean toggles a tighter or looser
bound on the integer variable.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & b \in \{0,1\},\ load \in \{0,\dots,19\} \\
   \text{Indicator capacity:}\quad & load - 8b \le 4 \\
   \text{Equivalent branches:}\quad &
      b=0 \Rightarrow load \le 4,\quad
      b=1 \Rightarrow load \le 12 \\
   \text{Objective:}\quad & \min \; 3(1-b) - value(load)
   \end{aligned}

Code
^^^^

.. literalinclude:: ../examples/model/17_big_m_indicator_capacity.py
   :language: python
   :caption: examples/model/17_big_m_indicator_capacity.py

Output
^^^^^^

The boolean activation and the resulting load demonstrate the conditional
capacity bound in a Big-M style model, compiled through the dedicated fast path.

.. literalinclude:: _generated/example_outputs/17_big_m_indicator_capacity.txt
   :language: console


Example 18: Running Watermark
-----------------------------

When to use this
^^^^^^^^^^^^^^^^

Show the ``running_max()`` helper, which packages the efficient cumulative-fold
pattern for prefix maxima and avoids the common quadratic prefix-max modelling
mistake.

Why this is efficient
^^^^^^^^^^^^^^^^^^^^^

The naive way to compute every prefix maximum recomputes larger and larger
prefixes independently. ``running_max()`` builds the sequence cumulatively,
which is the best construction pattern for ladder max aggregation.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.IntVector.running_max`

Model
^^^^^

The output vector is defined by:

.. math::

   \begin{aligned}
   r_0 &= x_0 \\
   r_i &= \max(r_{i-1}, x_i) \qquad i \ge 1
   \end{aligned}

Each prefix value is derived from the previous prefix maximum and the new item.

Code
^^^^

.. literalinclude:: ../examples/model/18_running_watermark.py
   :language: python
   :caption: examples/model/18_running_watermark.py

Output
^^^^^^

The watermark vector is the running prefix maximum of the input timeline.

.. literalinclude:: _generated/example_outputs/18_running_watermark.txt
   :language: console


Example 19: ``all_different``
------------------------------------------------

When to use this
^^^^^^^^^^^^^^^^

Use this when you care about modelling scalability and want to choose the right
``all_different`` backend for your domain size and vector length.

Both backends are semantically equivalent, but they scale differently. This
example shows how to compare them on the same model and inspect the resulting
CNF size, which is often the deciding factor on larger instances.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.IntVector.all_different` with backend selection

Model
^^^^^

Both backends encode the same logical constraint.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x_0,\dots,x_3 \in \{0,\dots,5\} \\
   \text{Constraint:}\quad & x_i \ne x_j \quad \forall i<j
   \end{aligned}

``pairwise`` uses scalar inequalities directly. ``bipartite`` channels to
exact-value indicators and adds per-value at-most-one constraints.

Code
^^^^

.. literalinclude:: ../examples/model/19_all_different_backends.py
   :language: python
   :caption: examples/model/19_all_different_backends.py

Output
^^^^^^

Both backends produce valid all-different solutions. The clause counts show the
kind of structural tradeoff this example is meant to compare.

.. literalinclude:: _generated/example_outputs/19_all_different_backends.txt
   :language: console


Example 20: Interval Scheduling
----------------------------------------------------

When to use this
^^^^^^^^^^^^^^^^

Use this as a template for small scheduling models where you want readable
interval constraints.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.Model.max` (explicit aggregate)
* Direct objective minimization of an integer aggregate

Model
^^^^^

This model combines interval-level disjunctive scheduling with a classic
makespan objective:

.. math::

   \begin{aligned}
   \text{Intervals:}\quad &
      A,B,C \text{ with fixed durations} \\
   \text{Hard constraints:}\quad &
      A \text{ and } B \text{ do not overlap}, \\
      & B \text{ and } C \text{ do not overlap}, \\
      & A \text{ ends before } B \\
   \text{Makespan:}\quad &
      M = \max(e_A, e_B, e_C) \\
   \text{Objective:}\quad & \min M
   \end{aligned}

The makespan is modeled explicitly as an aggregate variable and minimized
directly.

Code
^^^^

.. literalinclude:: ../examples/model/20_interval_makespan_watermark.py
   :language: python
   :caption: examples/model/20_interval_makespan_watermark.py

Output
^^^^^^

The printed interval assignments and makespan show a small but complete
scheduling optimization model with an explicit aggregate objective.

.. literalinclude:: _generated/example_outputs/20_interval_makespan_watermark.txt
   :language: console
