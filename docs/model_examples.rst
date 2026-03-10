Modelling Examples
==================================

Conventions
-----------

* Hermax solves **minimization** problems.
* ``model.obj[w] += lit`` adds a soft unit clause ``[lit]`` of weight ``w``.
* A soft unit clause ``[lit]`` pays cost ``w`` when ``lit`` is **false**.
* To penalize a Boolean decision ``x`` when it is true, use ``model.obj[w] += ~x``.

Example 01: Toy Soft Clauses
----------------------------



Introduce the basic MaxSAT workflow with hard clauses and weighted soft unit
clauses.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :class:`hermax.model.Model`
* :meth:`hermax.model.Model.bool`
* Hard constraints with ``model &=``
* Soft constraints with ``model.obj[w] +=``
* :meth:`hermax.model.Model.solve`

Model
^^^^^

This is the smallest useful weighted partial MaxSAT instance: a hard CNF core
plus a weighted set of soft preferences. It exposes Hermax's literal/soft-clause polarity convention without introducing
PB encoders or finite-domain variables.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & a,b,c \in \{0,1\} \\
   \text{Hard constraints:}\quad & (a \lor b)\ \land\ (\neg a \lor c) \\
   \text{Soft clauses:}\quad &
      (a, 3),\ (\neg b, 2),\ (c, 1) \\
   \text{Objective:}\quad &
      \min \sum_i w_i \cdot [\text{soft clause } i \text{ is violated}]
   \end{aligned}

Code
^^^^

.. literalinclude:: ../examples/model/01_toy_soft_clauses.py
   :language: python
   :caption: examples/model/01_toy_soft_clauses.py

Output
^^^^^^^^^^^^^^^^^^^^

This output shows one optimal assignment and the resulting weighted MaxSAT cost.

.. literalinclude:: _generated/example_outputs/01_toy_soft_clauses.txt
   :language: console


.. _example-knapsack:

Example 02: Knapsack
----------------------------------------------------



Show a weighted pseudo-Boolean capacity constraint and a MaxSAT objective that
maximizes profit by minimizing penalties for not selecting items.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :class:`hermax.model.BoolVector`
* PB expressions over booleans (``sum(w_i * x_i) <= C``)

Model
^^^^^

This is the first pseudo-boolean: one weighted capacity inequality and a
linear profit objective. Knapsack is one of Karp's original NP-complete
problems [1]_, and it is also a standard optimization reference problem in its
own right [2]_.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x_i \in \{0,1\}\ \text{(item selected)} \\
   \text{Capacity:}\quad &
      \sum_i \mathrm{weight}_i x_i \le C \\
   \text{Profit objective:}\quad &
      \max \sum_i \mathrm{profit}_i x_i \\
   \text{MaxSAT form:}\quad &
      \min \sum_i \mathrm{profit}_i (1 - x_i)
   \end{aligned}

The code uses soft unit clauses ``[x_i]`` so the cost is paid when ``x_i=0``, which is exactly the transformed minimization objective.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/knapsack_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (knapsack problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/02_knapsack_pb.py
   :language: python
   :caption: examples/model/02_knapsack_pb.py

Output
^^^^^^^^^^^^^^^^^^^^

The solver selects a feasible subset under the capacity constraint and reports
the chosen items.

.. literalinclude:: _generated/example_outputs/02_knapsack_pb.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/knapsack_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (knapsack solution). See the HTML docs for the diagram.*


.. _example-set-cover:

Example 03: Minimum Set Cover
-----------------------------



Model the classic minimum set cover problem using booleans, disjunctions, and
weighted soft penalties on selected sets.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :class:`hermax.model.BoolDict` (keyed booleans)
* :meth:`hermax.model.Model.vector` with :meth:`hermax.model.BoolVector.at_least_one`

Model
^^^^^

This is a weighted set-cover formulation. It is an example of disjunctions
over a dictionary of booleans and an objective tied
to selected decisions. Set cover is one of Karp's original NP-complete
problems [1]_ and is also a common problem in Garey and Johnson
[3]_.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x_S \in \{0,1\}\ \text{for each candidate set } S \\
   \text{Coverage constraints:}\quad &
      \bigvee_{S:\ u \in S} x_S \qquad \forall u \in U \\
   \text{Objective:}\quad &
      \min \sum_S c_S x_S
   \end{aligned}

The code encodes the objective with soft unit clauses ``[~x_S]``, so a
cost is paid when ``x_S`` is true.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/set_cover_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (set cover problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/03_set_cover.py
   :language: python
   :caption: examples/model/03_set_cover.py

Output
^^^^^^^^^^^^^^^^^^^^

The output shows a minimum-cost cover and the selected sets.

.. literalinclude:: _generated/example_outputs/03_set_cover.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/set_cover_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (set cover solution). See the HTML docs for the diagram.*


.. _example-vertex-cover:

Example 04: Minimum Vertex Cover
--------------------------------

Model weighted vertex cover on a small graph.

Model
^^^^^

Vertex cover is the graph analogue of set cover.
One clause per edge.
It is one of Karp's original NP-complete problems [1]_ and one of the
common graph problems in Garey and Johnson [3]_.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x_v \in \{0,1\}\ \text{(vertex } v \text{ is selected)} \\
   \text{Edge coverage:}\quad &
      x_u \lor x_v \qquad \forall (u,v)\in E \\
   \text{Objective:}\quad &
      \min \sum_{v \in V} c_v x_v
   \end{aligned}

As with the previous example, the code uses soft unit clauses ``[~x_v]`` so selecting a vertex
incurs its cost.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/vertex_cover_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (vertex cover problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/04_vertex_cover.py
   :language: python
   :caption: examples/model/04_vertex_cover.py

Output
^^^^^^^^^^^^^^^^^^^^

The solver returns one minimum-cost vertex cover for the small graph instance.

.. literalinclude:: _generated/example_outputs/04_vertex_cover.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/vertex_cover_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (vertex cover solution). See the HTML docs for the diagram.*


Example 05: Job Assignment
----------------------------------------------



Assign one worker to each task, enforce worker capacity, 
and minimize assignment cost.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :class:`hermax.model.EnumVar` / :class:`hermax.model.EnumDict`
* Enum equality literals ``(assign[t] == worker)``
* :meth:`hermax.model.BoolVector.at_most_one`

Model
^^^^^

A single typed variable per task replaces a full Boolean assignment matrix
while still exposing exact
equality literals for capacity and cost constraints. Unlike the NP-hard
examples above, the classical assignment problem is polynomial-time and is
famously solved by the Hungarian method [4]_.

.. math::

   \begin{aligned}
   \text{Variables:}\quad &
      a_t \in \{\text{alice},\text{bob},\text{carol}\} \\
   \text{Worker capacity:}\quad &
      \sum_t [a_t = w] \le 1 \qquad \forall w \\
   \text{Objective:}\quad &
      \min \sum_t \sum_w c_{t,w}\,[a_t = w]
   \end{aligned}

The bracket term ``[a_t = w]`` is realized in code by the literal
``(assign[t] == w)`` and softened as ``[~(assign[t] == w)]``.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/job_assignment_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (job assignment problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/05_job_assignment.py
   :language: python
   :caption: examples/model/05_job_assignment.py

Output
^^^^^^^^^^^^^^^^^^^^

This output shows one feasible assignment that respects worker capacity and the
resulting total cost.

.. literalinclude:: _generated/example_outputs/05_job_assignment.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/job_assignment_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (job assignment solution). See the HTML docs for the diagram.*


Example 06: Enum Subset Disjunction
-------------------------------------------------------



Demonstrate the fast categorical subset helper
:meth:`hermax.model.EnumVar.is_in`.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :meth:`hermax.model.EnumVar.is_in`

Model
^^^^^

The model isolates the categorical subset helper with a small optimization
target. This pattern appears frequently in scheduling models.

.. math::

   \begin{aligned}
   \text{Variable:}\quad &
      s \in \{\text{morning},\text{day},\text{night},\text{graveyard}\} \\
   \text{Subset constraint:}\quad &
      s \in \{\text{morning},\text{day}\} \\
   \text{CNF form:}\quad &
      [s=\text{morning}] \lor [s=\text{day}]
   \end{aligned}

Code
^^^^

.. literalinclude:: ../examples/model/06_enum_subset_shift.py
   :language: python
   :caption: examples/model/06_enum_subset_shift.py

Output
^^^^^^^^^^^^^^^^^^^^

The chosen shift is guaranteed to belong to the allowed subset.

.. literalinclude:: _generated/example_outputs/06_enum_subset_shift.txt
   :language: console


Example 07: Allowed Configurations
-----------------------------------------------------------



Model an extensional table constraint over a temporary
typed vector view.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :meth:`hermax.model.Model.vector` typed view
* :meth:`hermax.model.IntVector.is_in`

Model
^^^^^

This is an extensional constraint (table of valid tuples), a core CP modelling primitive.
The example uses a temporary typed vector view so the syntax stays
close to the mathematical statement.

.. math::

   \begin{aligned}
   \text{Decision vector:}\quad & \mathbf{x}=(cpu,ram,mobo) \\
   \text{Allowed table:}\quad & T=\{T_1,\dots,T_m\} \\
   \text{Constraint:}\quad & \mathbf{x} \in T \\
   \text{Encoding idea:}\quad &
      \exists s_1,\dots,s_m:\ \mathrm{ExactlyOne}(s_1,\dots,s_m) \\
      & \qquad\land \bigwedge_{i=1}^m \left(s_i \rightarrow (\mathbf{x}=T_i)\right)
   \end{aligned}

The current implementation uses row-selector literals, deduplicates repeated
rows, and gates each row with exact scalar equalities.

Code
^^^^

.. literalinclude:: ../examples/model/07_table_allowed_configs.py
   :language: python
   :caption: examples/model/07_table_allowed_configs.py

Output
^^^^^^^^^^^^^^^^^^^^

The selected configuration is one of the allowed table rows.

.. literalinclude:: _generated/example_outputs/07_table_allowed_configs.txt
   :language: console


Example 08: Element Constraint (``@``)
---------------------------------------------------------



Show the CP element constraint using lazy array indexing:
``array @ int_var``.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* ``array @ int_var`` lazy multiplexer descriptor

Model
^^^^^

This is the element-constraint pattern from CP: select a constant from an array
using an integer variable, then constrain the selected value. The lazy ``@``
descriptor avoids introducing a separate "selected-cost" integer variable.

.. math::

   \begin{aligned}
   \text{Given:}\quad & costs = [c_0,\dots,c_{n-1}] \\
   \text{Variables:}\quad & w \in \{0,\dots,n-1\},\ budget \\
   \text{Constraint:}\quad & costs[w] \le budget \\
   \text{Compilation idea:}\quad &
      \bigwedge_{k=0}^{n-1} \left((w=k) \rightarrow (c_k \le budget)\right)
   \end{aligned}

For constant right-hand sides, the implementation simplifies this further into
domain filtering (forbidding impossible index values).

Problem
^^^^^^^

.. only:: html

   .. image:: _static/element_constraint_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (element constraint problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/08_multiplexer_budget.py
   :language: python
   :caption: examples/model/08_multiplexer_budget.py

Output
^^^^^^^^^^^^^^^^^^^^

This output shows the chosen index and the selected cost value constrained by
the budget.

.. literalinclude:: _generated/example_outputs/08_multiplexer_budget.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/element_constraint_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (element constraint solution). See the HTML docs for the diagram.*


Example 09: Sudoku (9x9)
------------------------------------------------------------------



Demonstrate matrix modelling, NumPy-like slicing, and ``all_different`` on rows,
columns, and 3x3 subgrids.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :class:`hermax.model.EnumMatrix`
* NumPy-like indexing (``grid[r, :]``, ``grid[:, c]``, ``grid[a:b, c:d]``)
* ``flatten()`` on matrix views
* :meth:`hermax.model.EnumVector.all_different`

Model
^^^^^

Matrix-focused example. The instance uses a fixed puzzle, so rows, columns, and
3x3 boxes are easy to inspect with the same typed-vector operations.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x_{r,c} \in \{\texttt{"1"},\dots,\texttt{"9"}\} \\
   \text{Row constraints:}\quad &
      \mathrm{AllDifferent}(x_{r,1},\dots,x_{r,9}) \qquad \forall r \\
   \text{Column constraints:}\quad &
      \mathrm{AllDifferent}(x_{1,c},\dots,x_{9,c}) \qquad \forall c \\
   \text{Block constraints:}\quad &
      \mathrm{AllDifferent}(\text{cells in each } 3\times3 \text{ block}) \\
   \text{Clues:}\quad & \text{9x9 puzzle instance}
   \end{aligned}

.. warning::

   Sudoku "digits" are better modeled as enums than as ints.
   The puzzle is really about exact symbols, not about arithmetic values.
   If sudoku had letters instead of digits, it would be played the same way,
   so the numeric nature of the symbols is not relevant to the combinatorial search.
   Using enums is more efficient when possible.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/sudoku_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (sudoku problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/09_sudoku9_single_clue.py
   :language: python
   :caption: examples/model/09_sudoku9_single_clue.py

Output
^^^^^^^^^^^^^^^^^^^^

The output shows the deterministic completion of the fixed puzzle instance.

.. literalinclude:: _generated/example_outputs/09_sudoku9_single_clue.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/sudoku_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (sudoku solution). See the HTML docs for the diagram.*


Example 10: No Overlap Scheduling
--------------------------------------------

Show scheduling constraints with object interval methods.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :class:`hermax.model.IntervalVar`
* :meth:`hermax.model.Model.interval`
* :meth:`hermax.model.IntervalVar.ends_before`, :meth:`hermax.model.IntervalVar.no_overlap`

Model
^^^^^

This model uses a scheduling oriented API layer built on top of ladder
integers. ``IntervalVar`` keeps the model readable while compiling to plain
SAT/MaxSAT constraints.

.. math::

   \begin{aligned}
   \text{For each task } i:\quad &
      s_i = \text{start},\ e_i = \text{end},\ d_i=\text{fixed duration} \\
   \text{Interval identity:}\quad &
      e_i = s_i + d_i \\
   \text{Non-overlap:}\quad &
      e_i \le s_j \ \lor\ e_j \le s_i \\
   \text{Preference (example):}\quad &
      \min s_C
   \end{aligned}

Internally, the interval identity is compiled with a direct ladder-bit weld
(linear number of binary clauses, zero auxiliary variables), not with a generic
PB/Card equality encoder.

Code
^^^^

.. literalinclude:: ../examples/model/10_interval_scheduling.py
   :language: python
   :caption: examples/model/10_interval_scheduling.py

Output
^^^^^^^^^^^^^^^^^^^^

The printed intervals confirm the no-overlap and precedence constraints.

.. literalinclude:: _generated/example_outputs/10_interval_scheduling.txt
   :language: console


Example 11: Int Variables in the Objective
-------------------------------------------------------



Demonstrate ``obj[w] += int_var`` (ladder-bit objective lowering) combined with
hard PB constraints.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* ``model.obj[w] += int_var`` with :class:`hermax.model.IntVar`

Model
^^^^^

This model shows typed finite-domain variables in the MaxSAT objective
without introducing a separate arithmetic backend API.

.. math::

   \begin{aligned}
   \text{Variables:}\quad & x,y \in \mathbb{Z}\ \text{(bounded IntVar)},\ b \in \{0,1\} \\
   \text{Hard constraints:}\quad &
      x+y \ge 8,\quad x+2y \le 14,\quad x+b \le 6 \\
   \text{Objective:}\quad &
      \min (3x + y + 2b)
   \end{aligned}

``model.obj[w] += x`` is lowered to soft clauses over the ladder threshold bits
of ``x`` (linear in the ladder width), plus a constant offset contribution from
the lower bound.

Code
^^^^

.. literalinclude:: ../examples/model/11_int_objective.py
   :language: python
   :caption: examples/model/11_int_objective.py

Output
^^^^^^^^^^^^^^^^^^^^

This output shows a solution minimizing an objective that includes
integer variables and a boolean penalty.

.. literalinclude:: _generated/example_outputs/11_int_objective.txt
   :language: console

.. _example-wifi:

Example 12: WiFi Channel Assignment
-------------------------------------------------------



Show a compact domain model using nullable enum states for router channels, hard interference constraints, and soft penalties.
Inspired on [5]_ and [6]_, this is a simplified version of the WiFi channel assignment.

New primitives
^^^^^^^^^^^^^^^^^^^^^^^^^^

* :class:`hermax.model.EnumDict` with ``nullable=True``
* Practical composition of enum equality literals and soft penalties

Model
^^^^^

This model combines nullable enums, graph
constraints, and soft penalties. It is a good example after the
smaller, isolated primitives explored earlier on this page.

.. math::

   \begin{aligned}
   \text{Variables:}\quad &
      state_r \in \{f_1,f_2,f_3\}\cup\{\text{offline}\} \qquad \forall r \\
   \text{Interference hard constraints:}\quad &
      \neg(state_u=f)\ \lor\ \neg(state_v=f)
      \qquad \forall (u,v)\in E,\ \forall f \\
   \text{Soft penalties:}\quad &
      \text{offline penalties} + \text{per-frequency usage penalties}
   \end{aligned}

The model uses nullable enums so "offline" is represented as the
absence of a selected frequency (decoded as ``None``), rather than as an extra
binary-variable layer.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/wifi_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (wifi problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/12_wifi_nullable_enum.py
   :language: python
   :caption: examples/model/12_wifi_nullable_enum.py

Output
^^^^^^^^^^^^^^^^^^^^

The result shows router states and the resulting objective cost.

.. literalinclude:: _generated/example_outputs/12_wifi_nullable_enum.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/wifi_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (wifi solution). See the HTML docs for the diagram.*

Next
----

Advanced modelling examples continue in :doc:`model_examples_tricks`.



References
----------

.. [1] Richard M. Karp. *Reducibility among combinatorial problems*. In
   *Complexity of Computer Computations*, pages 85--103. Springer, 1972.
.. [2] Silvano Martello and Paolo Toth. *Knapsack Problems: Algorithms and
   Computer Implementations*. John Wiley & Sons, 1990.
.. [3] Michael R. Garey and David S. Johnson. *Computers and Intractability:
   A Guide to the Theory of NP-Completeness*. W. H. Freeman, 1979.
.. [4] Harold W. Kuhn. *The Hungarian method for the assignment problem*.
   *Naval Research Logistics Quarterly*, 2(1-2):83--97, 1955.
.. [5] H. Birkan Yilmaz, Bon-Hong Koo, Sung-Ho Park, Hwi-Sung Park,
   Jae-Hyun Ham, Chan-Byoung Chae.
   *Frequency assignment problem with net filter discrimination constraints*.
   arXiv preprint arXiv:1605.04379, 2016.
.. [6] David Orden, José Manuel Giménez-Guzmán, Ivan Marsa-Maestre,
   Enrique de la Hoz.
   *Spectrum graph coloring and applications to Wi-Fi channel assignment*.
   *Symmetry*, 10(3):65, 2018.
