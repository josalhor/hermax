Modelling Tricks
================

Practical patterns implemented by :mod:`hermax.model`.

Core idea:

* keep ladder structure when possible,
* avoid generic PB/Card encoders when a tighter encoding exists,
* keep expressions lazy,
* materialize only at model sinks (``model &= ...``,
  ``model.obj[...] += ...``, export/solve).


Scalar and Pairwise Tricks
----------------------------------------

These use threshold literals directly.

* ``IntVar == IntVar``:
  threshold-wise equivalence, linear in domain width.

* ``IntVar != IntVar``:
  overlap-value forbidding with compact clauses (no aux variables).

* ``IntVar <=, <, >=, > IntVar``:
  direct threshold implications and strict variants (no PB encoder).

* Full Boolean reification:
  ``b == (x <= y)`` (and ``<, >=, >``) compiles to two conditional native branches.

* ``IntVar.distance_at_most(other, D)``:
  ``|X-Y| <= D`` via shifted threshold implications, zero aux vars.

* ``IntVar.forbid_value(v)``:
  forbids one value using one small clause.

* ``IntVar.forbid_interval(start, end)``:
  removes a contiguous block using one jump implication.

* ``IntVar.in_range(start, end)``:
  returns a reusable lazy indicator literal for inclusive range membership.

* ``IntVar // const``:
  floor-division by a positive constant via threshold remapping
  ``(q >= m) <-> (x >= m*d)``.


Aggregates and Prefix Patterns
-------------------------------------

These avoid generic arithmetic encodings.

* ``IntVector.max()`` / ``IntVector.min()`` (lazy wrappers) and
  ``Model.max(...)`` / ``Model.min(...)`` (eager):
  threshold-wise OR/AND.

* ``IntVector.upper_bound()`` / ``lower_bound()``:
  one-sided aggregate bounds, cheaper than exact ``max/min`` when only one
  direction is needed.

* ``IntVector.running_max()`` / ``running_min()``:
  cumulative-fold helpers for prefix extrema.


Pseudo Boolean (PB) Tricks
----------------------------

* Lazy PB comparators:
  comparisons return :class:`hermax.model.PBConstraint`, compiled only on
  demand.

* ``PBConstraint.only_if(...)`` / ``PBConstraint.implies(...)``:
  half-reified/gated meaning.

* ``PBExpr`` scalar multiplication:
  expressions like ``2 * (x + y + 1)`` stay lazy.

* Compiler GCD normalization:
  coefficients and bounds are reduced before dispatch, improving cardinality
  hit rate and shrinking PB instances [1]_.

* PB/Card compare compile cache:
  normalized comparator shapes are cached, so repeated equivalent PB/Card
  constraints reuse compiled clause groups.

* Duplicate term collapsing in ``PBExpr``:
  merges repeated terms (e.g. ``a + b + 2*b`` -> ``a + 3*b``).


PB Objective Tricks
-------------------

Objective lowering avoids unnecessary proxy variables.

* Direct ``PBExpr`` objective lowering:
  ``model.obj[w] += pbexpr`` lowers to weighted soft unit clauses plus an
  objective offset.

* ``IntVar`` objective lowering:
  ``model.obj[w] += x`` lowers to threshold soft units (ladder bits), linear in
  domain width, plus an offset.

* ``IntVar.piecewise(...)`` objective use:
  minimize step costs directly without proxy integers.

Piecewise and Step-Function Tricks
----------------------------------

``IntVar.piecewise(base_value, steps)`` maps an integer to a step function as a
lazy ``PBExpr`` using threshold deltas:

.. math::

   f(x) = c_0 + \sum_t \Delta_t \,[x \ge t]

Notable properties:

* zero new variables and zero clauses at construction time,
* works for monotonic and non-monotonic step functions,
* negative deltas are handled by PB normalization,
* composes directly into constraints and objectives.


Compiler Fast Paths
-------------------

The compiler recognizes structured forms and emits ladder clauses directly.

* Univariate affine fast path:
  ``a*X OP C`` (``OP`` in ``<=,<,>=,>,==``), compiled to boundary literals or
  small clause groups without PB/Card.

* Univariate + boolean (Big-M) fast path:
  ``a*X + w*b OP C`` splits into two conditional univariate branches; avoids generic
  PB for common indicator constraints.

* Unified bivariate affine fast path:
  ``a*X + b*Y OP C`` compiled with a threshold cliff tracer and zero helper
  variables (supersedes older offset/scaled special cases).

* Trivariate sum fast path:
  ``X + Y <= Z`` and ``X + Y < Z`` are compiled directly with ladder-threshold
  implications (binary/ternary clauses), avoiding generic PB/Card.

* Bool-sum to IntVar channeling fast path:
  ``X + c_1 OP (b_1 + \dots + b_n) + c_2`` for
  ``OP in {==, <=, >=, <, >}`` (unit boolean coefficients), compiled with a
  sequential counter and directional ladder channeling.

* Specialized offset/scaled relations are handled by the unified bivariate path,
  keeping the compiler simpler and less leak-prone.


Collection and Table Tricks
---------------------------

CP-style conveniences compiled into flat CNF/PB-friendly forms.

* ``EnumVar.is_in(...)``:
  fast subset membership as a flat CNF clause over existing choice literals.

* ``Vector.is_in(rows)``:
  allowed-combinations table constraint via row selectors +
  exactly-one + conditional row implications.

* ``IntVector[IntVar]`` element access:
  variable-index branch gating ``(idx=i) -> (vals_i OP rhs)`` for
  ``OP in {==, !=, <=, <, >=, >}``.

* ``EnumVector.all_different(backend=\"bipartite\")``:
  column-wise AMO on existing enum choice literals (no extra row variables).

* ``IntVector.all_different(backend=\"bipartite\")``:
  exact-value indicator channeling + value-column AMOs (alternative to pairwise
  ``!=`` in some regimes).


Matrix and Scheduling Tricks
----------------------------

* NumPy-style matrix indexing and slicing:
  ``grid[r, c]``, ``grid[:, j]``, ``grid[r0:r1, c0:c1].flatten()`` for clean
  CP-style subset constraints.

* ``IntervalVar`` fixed-duration weld:
  ``end == start + duration`` is encoded by tying ladder thresholds directly,
  avoiding generic PB/Card equality for this relation.

References
----------

.. [1] Niklas Eén, Niklas Sörensson. *Translating pseudo-boolean constraints into SAT*. Journal on Satisfiability, Boolean Modelling and Computation, 2(1-4):1-26, 2006.
