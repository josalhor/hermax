Advanced Modelling Examples
==========================================================

This page continues :doc:`model_examples`. Start there for the basics.

Conventions
-----------

* Hermax solves **minimization** problems.
* ``model.obj[w] += expr`` minimizes the numeric value of ``w * expr``.
* ``IntVar`` values are bounded over closed domains ``[lb, ub]``.
* ``x >= k`` in the implementation corresponds to a ladder threshold literal.


Example 13: Piecewise
--------------------------------------


Use this when a cost depends on integer tiers and appears in constraints or the
objective.

Efficiency
^^^^^^^^^^^^^^^^^^^^^

The expression uses the integer variable's existing ladder literals. It does
not create another integer variable, so budget models need fewer clauses.

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



Use this to count values in integer buckets for constraints or objectives.

Efficiency
^^^^^^^^^^^^^^^^^^^^^

``in_range()`` returns a Boolean indicator for an interval. Sum these
indicators to count each bucket.

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

The output shows the chosen completion times, and the three bin
counts match the target histogram exactly.

.. literalinclude:: _generated/example_outputs/14_histogram_binning.txt
   :language: console


Example 15: Domain Holes and Distance Bound
-------------------------------------------



Use this when the domain has simple forbidden ranges or distance rules. The
ladder encoding can express them without a generic PB constraint.

Efficiency
^^^^^^^^^^^^^^^^^^^^^

These constraints use small clause sets, even when the domain is large.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.IntVar.forbid_interval`
* :meth:`hermax.model.IntVar.forbid_value`
* :meth:`hermax.model.IntVar.distance_at_most`

Model
^^^^^

This model is constraint heavy and uses ladder operations.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x,y \in \{0,\dots,29\} \\
   \text{Holes:}\quad & x \notin [10,20],\quad y \neq 11 \\
   \text{Proximity:}\quad & |x-y| \le 2 \\
   \text{Objective:}\quad & \min \; -score(x) - score(y)
   \end{aligned}

where ``score`` is expressed with ``piecewise(...)`` and lowered as a
target-preference expression in the objective.

Code
^^^^

.. literalinclude:: ../examples/model/15_domain_holes_and_distance.py
   :language: python
   :caption: examples/model/15_domain_holes_and_distance.py

Output
^^^^^^

The solution satisfies the distance bound and avoids both domain
holes.

.. literalinclude:: _generated/example_outputs/15_domain_holes_and_distance.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: /_static/domain_holes_distance_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (domain-holes + distance solution). See the HTML docs for the diagram.*


Example 16: Division and Scaling
-------------------------------------------------------



Use this when your model has coarse units or derived values but you want normal
algebraic syntax.

Efficiency
^^^^^^^^^^^^^^^^^^^^^

The compiler maps these forms to ladder fast paths instead of generic PB/Card
encoders. This reduces auxiliary variables in scheduling and resource models.

New primitives
^^^^^^^^^^^^^^

* ``x // d`` (division expression)
* ``x.scale(c)`` (scaling/multiplication expression)

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

.. literalinclude:: _generated/example_outputs/16_lazy_div_scale_affine.txt
   :language: console


Example 17: Big-M
-------------------------------------



Use this for the classic Operations Research pattern: a Boolean switch changes
an integer bound.
This appears in optional resources, setup dependent capacities, and other
Big M formulations.

Efficiency
^^^^^^^^^^^^^^^^^^^^^

The pattern uses two conditional ladder bounds instead of a generic PB encoding,
so it needs fewer clauses and auxiliary variables.

Model
^^^^^

The user writes ordinary syntax. The boolean toggles a tighter or looser
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

The boolean activation and the resulting load show the conditional
capacity bound in a Big-M style model, compiled through the dedicated fast path.

.. literalinclude:: _generated/example_outputs/17_big_m_indicator_capacity.txt
   :language: console


Example 18: Running Maximum
-----------------------------



Show ``running_max()``, which builds prefix maxima with a cumulative fold.

Efficiency
^^^^^^^^^^^^^^^^^^^^^

Computing each prefix independently repeats work. ``running_max()`` builds the
sequence one item at a time.

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



Use this to compare the ``all_different`` backends for your domain and vector
size.

Both backends are equivalent but have different clause counts. The example
compares them on the same model.

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
value indicators and adds per-value AMO constraints.

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



Use this as a template for small scheduling models with readable interval
constraints.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.Model.max` (explicit aggregate)
* Direct objective minimization of an integer aggregate

Model
^^^^^

This model combines interval-level disjunctive scheduling with a 
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

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/interval_scheduling_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (interval scheduling solution). See the HTML docs for the diagram.*


Example 21: Decode Collections
------------------------------



Use this when the model contains vectors, matrices, dictionaries, or enum
collections and you want ordinary Python values from the result.

The model fixes entries in a small integer vector, integer matrix, Boolean
dictionary, and enum dictionary, then decodes them to Python containers.

Code
^^^^

.. literalinclude:: ../examples/model/21_decode_collections.py
   :language: python
   :caption: examples/model/21_decode_collections.py

Output
^^^^^^

The result object decodes each collection into the matching Python container.

.. literalinclude:: _generated/example_outputs/21_decode_collections.txt
   :language: console


Example 22: Indexed Lookup
--------------------------



Use this when one decision chooses a value from a table. Common cases are
machine processing times, worker costs, or plan limits.

New primitives
^^^^^^^^^^^^^^

* variable-index element constraints with ``vec[idx]``

Model
^^^^^

Each job chooses one machine. The chosen machine determines the processing
time through a table lookup.

.. math::

   \begin{aligned}
   \text{Variables:}\quad &
      m_j \in \{0,\dots,k-1\}\ \text{(machine chosen for job } j\text{)} \\
   \text{Lookup:}\quad &
      p_j = duration_j[m_j] \\
   \text{Objective:}\quad &
      \min \sum_j p_j
   \end{aligned}

This fits data already stored as Python lists or vectors.

.. warning::

   Indexed lookup is a good fit for small tables and menu choices, but it
   does not scale well. Use it when the lookup itself is the natural model. For
   large tables or many repeated lookups, prefer a formulation with more direct
   structure if one is available.

Code
^^^^

.. literalinclude:: ../examples/model/22_indexed_lookup.py
   :language: python
   :caption: examples/model/22_indexed_lookup.py

Output
^^^^^^

The solver chooses the cheapest allowed machine and returns the matched value
from the duration table.

.. literalinclude:: _generated/example_outputs/22_indexed_lookup.txt
   :language: console


Example 23: Optional Assignment
-------------------------------



Use this when an item may be assigned to a resource, but leaving it unassigned
is also allowed with a penalty.

Many real problems are not "assign everything no matter what". This pattern is
better for overload planning, staff shortages, fallback scheduling, and
"serve the most important requests first" problems.

New primitives
^^^^^^^^^^^^^^

* nullable :class:`hermax.model.EnumVar`
* enum equality literals ``(assign[t] == worker)``

Model
^^^^^

Each task is assigned to one worker, or to ``None`` if it is left unassigned.
Leaving a task unassigned pays a penalty.

.. math::

   \begin{aligned}
   \text{Variables:}\quad &
      a_t \in W \cup \{\text{None}\} \\
   \text{Capacity:}\quad &
      \sum_t [a_t = w] \le cap_w \qquad \forall w \in W \\
   \text{Penalty for skipping work:}\quad &
      penalty_t \cdot [a_t = \text{None}] \\
   \text{Objective:}\quad &
      \min \sum_t penalty_t [a_t = \text{None}]
      + \sum_{t,w} c_{t,w}[a_t = w]
   \end{aligned}

This is easier to read than a Boolean assignment matrix when each item can go
to at most one place.

Code
^^^^

.. literalinclude:: ../examples/model/23_optional_assignment.py
   :language: python
   :caption: examples/model/23_optional_assignment.py

Output
^^^^^^

The result leaves the least important task unassigned and decodes that choice
as ``None``.

.. literalinclude:: _generated/example_outputs/23_optional_assignment.txt
   :language: console


Example 24: Facility Location
-----------------------------

Use this when opening a site has a fixed cost, and each client must be attached
to one open site.

This combines open or close decisions, assignments, and fixed costs.

New primitives
^^^^^^^^^^^^^^

* booleans for opening sites
* enums for client assignment
* linking constraints between assignment and activation

Model
^^^^^

Each facility may be opened or closed. Each client is assigned to one facility.
Assignments are only allowed to open facilities.

.. math::

   \begin{aligned}
   \text{Variables:}\quad &
      open_f \in \{0,1\},\quad a_c \in F \\
   \text{Open-link rule:}\quad &
      [a_c = f] \Rightarrow open_f \qquad \forall c,f \\
   \text{Capacity:}\quad &
      \sum_c demand_c [a_c = f] \le cap_f \cdot open_f \qquad \forall f \\
   \text{Objective:}\quad &
      \min \sum_f fixed_f\,open_f + \sum_{c,f} ship_{c,f}[a_c = f]
   \end{aligned}

The same structure appears in
warehouses, server placement, clinic selection, and planning problems.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/facility_location_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (facility location problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/24_facility_location.py
   :language: python
   :caption: examples/model/24_facility_location.py

Output
^^^^^^

The solver opens the cheaper facility and routes every client through it.

.. literalinclude:: _generated/example_outputs/24_facility_location.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/facility_location_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (facility location solution). See the HTML docs for the diagram.*


Example 25: Portfolio Solve
---------------------------



Use this when the model is already written and you want a better default solve
strategy without manually choosing a single backend.

* :meth:`hermax.model.Model.solve` with ``solver=CompletePortfolioSolver``
* ``solver_kwargs`` for solver selection and worker settings

Solver performance can vary a lot from one model family to another. A
portfolio lets you keep the same model and try several solvers behind the same
interface.

The constraints and objective stay the same; only the solve strategy changes.


Code
^^^^

.. literalinclude:: ../examples/model/25_portfolio_solve.py
   :language: python
   :caption: examples/model/25_portfolio_solve.py



.. warning::

   Hermax provides broader portfolio presets, including incomplete
   solvers. Those can be useful for speed, but they need more care: incomplete
   backends do not carry the exactness guarantees as
   the complete preset used in this example.

For the full portfolio API, preset classes, and selection policies, see
:doc:`portfolio`.

Output
^^^^^^

The model is unchanged; only the solve strategy is switched to a portfolio
wrapper.

.. literalinclude:: _generated/example_outputs/25_portfolio_solve.txt
   :language: console


Example 29: Floating Point Objective
------------------------------------

Use this when constraints are discrete but objective terms are fractional, such
as prices, rates, or probabilities.

Keep objective terms in natural units instead of scaling them by hand.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.Model.set_objective_precision`
* floating-point objective weights via ``model.obj[w] += ...``

Model
^^^^^

Capital budgeting variant: choose projects under a developer-month capacity and
maximize expected ROI (millions USD). Since Hermax minimizes, the model
minimizes missed ROI:

.. math::

   \begin{aligned}
   \min \quad & \sum_{p} roi_p \cdot [\neg fund_p] \\
   \text{s.t.}\quad & \sum_{p} months_p \cdot [fund_p] \le 18
   \end{aligned}

Problem
^^^^^^^

.. only:: html

   .. image:: _static/float_objective_budgeting_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (float-objective budgeting problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/29_float_objective_budgeting.py
   :language: python
   :caption: examples/model/29_float_objective_budgeting.py

.. note::

   Floating objective weights require explicit precision setup, for example
   ``set_objective_precision(decimals=2)``.

Output
^^^^^^

The output reports missed ROI (optimization cost) and selected ROI in the same
units.

.. literalinclude:: _generated/example_outputs/29_float_objective_budgeting.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/float_objective_budgeting_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (float-objective budgeting solution). See the HTML docs for the diagram.*


Example 30: Incremental Queries
-------------------------------

Use this when you solve once, add a new constraint from updated conditions, and
solve again.

You can iterate on one live model with three incremental operations:
hard updates, temporary assumptions, and objective updates.

Model
^^^^^

A small assignment model is solved in multiple passes:

1. Baseline solve
2. Hard update: forbid ``T2 -> M1``
3. What-if query with assumptions: force ``T1 -> M2`` temporarily
4. Objective replacement (automatic objective diffing)

Code
^^^^

.. literalinclude:: ../examples/model/30_incremental_rescheduling.py
   :language: python
   :caption: examples/model/30_incremental_rescheduling.py

Output
^^^^^^

The transcript shows that assumptions do not persist, while hard/objective
updates do.

.. literalinclude:: _generated/example_outputs/30_incremental_rescheduling.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/incremental_queries_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (incremental-query timeline). See the HTML docs for the diagram.*


Example 31: Hierarchical Objectives
-----------------------------------


Use this when one objective strictly dominates another.

Lexicographic optimization avoids weighting hacks and enforces
priority order.

Model
^^^^^

Assignment scenario with two objective tiers:

* Tier 0: minimize unassigned VIP clients
* Tier 1: minimize travel cost

The model uses:

.. code-block:: python

   m.tier_obj.set_lexicographic(unassigned_vips, travel)

Problem
^^^^^^^

.. only:: html

   .. image:: _static/hierarchical_objectives_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (hierarchical-objective problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/31_hierarchical_objectives.py
   :language: python
   :caption: examples/model/31_hierarchical_objectives.py

Output
^^^^^^

The result reports per-tier costs through ``SolveResult.tier_costs``.

.. literalinclude:: _generated/example_outputs/31_hierarchical_objectives.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/hierarchical_objectives_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (hierarchical-objective solution). See the HTML docs for the diagram.*

.. note::

   This example uses ``solve(lex_strategy="incremental")`` (the default for
   tiered objectives), which optimizes tier by tier and hardens each optimum
   before moving to the next tier.

   ``lex_strategy="stratified"`` is also available and solves a single
   stratified objective. It might be faster on some instances (or not, YMMV).


Next
----

For NP-hard optimization examples, continue in :doc:`np_problems`.
