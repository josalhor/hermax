NP-Hard Problems
================

This page collects examples and patterns for classic NP-hard optimization
problems.

Several basic examples are already covered in the existing
galleries:

* :ref:`example-knapsack` for 0/1 knapsack
* :ref:`example-set-cover` for minimum set cover
* :ref:`example-vertex-cover` for minimum vertex cover
* :ref:`example-wifi` for graph-coloring channel assignment
* :ref:`example-cvrp` for routing with MTZ load constraints


Example 01: Job Shop Scheduling
-------------------------------

A job shop scheduling model with machine conflicts, per-job
operation order, and a makespan objective.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.Model.interval`
* :meth:`hermax.model.IntervalVar.ends_before`
* :meth:`hermax.model.IntervalVar.no_overlap`
* :meth:`hermax.model.Model.upper_bound`

Model
^^^^^

Each job is a sequence of operations. Each operation must run on one
machine for a given duration, operations of the same job must respect their
order, and operations that share a machine cannot overlap.

.. math::

   \begin{aligned}
   \text{Operations:}\quad & O_{j,1},\dots,O_{j,k_j} \\
   \text{Job precedence:}\quad & O_{j,t} \text{ ends before } O_{j,t+1} \\
   \text{Machine capacity:}\quad &
      O_{j,t} \text{ and } O_{j',t'} \text{ do not overlap if they use the same machine} \\
   \text{Makespan upper bound:}\quad &
      \mathrm{end}(O_{j,k_j}) \le M \qquad \forall j \\
   \text{Objective:}\quad & \min M
   \end{aligned}

This is one of the classic NP-hard scheduling problems [5]_, and it is a good
fit for interval variables because the model is fundamentally about start
times, end times, and resource conflicts.

.. note::

   This example uses :meth:`hermax.model.Model.upper_bound` instead of an exact
   ``max(...)`` aggregate. Under minimization, that is often the cleanest way
   to model makespan: the optimizer will push the upper bound down to the true
   schedule end automatically. An exact aggregate is still useful when the
   maximum value itself needs to be reused elsewhere in the model.

Code
^^^^

.. literalinclude:: ../examples/model/26_job_shop_scheduling.py
   :language: python
   :caption: examples/model/26_job_shop_scheduling.py

Output
^^^^^^

The printed schedule shows the operation order inside each job and the final
makespan.

.. image:: _static/jssp_solution.svg
   :alt: Job Shop scheduling solution chart
   :align: center
   :class: only-light

.. image:: _static/jssp_solution.svg
   :alt: Job Shop scheduling solution chart
   :align: center
   :class: only-dark

.. literalinclude:: _generated/example_outputs/26_job_shop_scheduling.txt
   :language: console

Example 02: Bin Packing
-----------------------

A bin packing model with item-to-bin assignment variables, bin
capacity constraints, and symmetry break.

New primitives
^^^^^^^^^^^^^^

* :meth:`hermax.model.Model.bool_matrix`
* :meth:`hermax.model.Model.bool_vector`
* :meth:`hermax.model.BoolVector.exactly_one`
* :meth:`hermax.model.Literal.implies`

Model
^^^^^

Each item must go in exactly one bin. Every bin has the same capacity. The
objective is to minimize the number of bins used.

.. math::

   \begin{aligned}
   \text{Variables:}\quad &
      x_{i,b} \in \{0,1\}\ \text{(item } i \text{ is placed in bin } b\text{)} \\
      & u_b \in \{0,1\}\ \text{(bin } b \text{ is used)} \\
   \text{Assignment:}\quad &
      \sum_b x_{i,b} = 1 \qquad \forall i \\
   \text{Capacity:}\quad &
      \sum_i size_i x_{i,b} \le C \qquad \forall b \\
   \text{Linking:}\quad &
      x_{i,b} \Rightarrow u_b \qquad \forall i,b \\
   \text{Symmetry break:}\quad &
      u_{b+1} \Rightarrow u_b \qquad \forall b \\
   \text{Objective:}\quad &
      \min \sum_b u_b
   \end{aligned}

Bin packing is an NP-hard problem [1]_, and it is also a common
benchmark for approximation algorithms [2]_.

.. note::

   The symmetry break says that bin ``b+1`` cannot be used unless bin ``b`` is
   already used. This does not change the set of achievable packings, but it
   removes many equivalent bin permutations and usually helps search.

Code
^^^^

.. literalinclude:: ../examples/model/27_bin_packing.py
   :language: python
   :caption: examples/model/27_bin_packing.py

Output
^^^^^^

The result shows the number of bins used and one concrete packing.

.. literalinclude:: _generated/example_outputs/27_bin_packing.txt
   :language: console


Example 03: Maximum Clique
--------------------------

A graph model where the goal is to select the largest fully connected
group of vertices.

New primitives
^^^^^^^^^^^^^^

* :class:`hermax.model.BoolDict`
* Hard clauses over graph decisions
* Soft unit objective terms for cardinality maximization

Model
^^^^^

Each vertex has one Boolean decision. If two vertices are not connected by an
edge, they cannot both belong to the clique. The objective is to maximize the
number of selected vertices.

.. math::

   \begin{aligned}
   \text{Variables:}\quad &
      x_v \in \{0,1\}\ \text{(vertex } v \text{ is in the clique)} \\
   \text{Non-edge constraints:}\quad &
      \neg x_u \lor \neg x_v
      \qquad \forall \{u,v\} \notin E \\
   \text{Objective:}\quad &
      \max \sum_{v \in V} x_v
   \end{aligned}

The maximum clique problem is one of Karp's original NP-complete problems [3]_
and is a common graph optimization benchmark [4]_.

.. note::

   Maximum clique and maximum independent set are two sides of the same graph
   idea. An independent set in a graph is a clique in its complement.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/max_clique_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (max clique problem). See the HTML docs for the diagram.*

Code
^^^^

.. literalinclude:: ../examples/model/28_maximum_clique.py
   :language: python
   :caption: examples/model/28_maximum_clique.py

Output
^^^^^^

The result shows one maximum clique found in the example graph.

.. literalinclude:: _generated/example_outputs/28_maximum_clique.txt
   :language: console

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/max_clique_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (max clique solution). See the HTML docs for the diagram.*


References
----------

.. [1] Michael R. Garey and David S. Johnson. *Computers and Intractability:
   A Guide to the Theory of NP-Completeness*. W. H. Freeman, 1979.
.. [2] Edward G. Coffman Jr., Michael R. Garey, and David S. Johnson.
   *Approximation algorithms for bin packing: A survey*. In
   *Approximation Algorithms for NP-hard Problems*, pages 46--93.
   PWS Publishing Co., 1996.
.. [3] Richard M. Karp. *Reducibility among combinatorial problems*. In
   *Complexity of Computer Computations*, pages 85--103. Springer, 1972.
.. [4] Immanuel M. Bomze, Marco Budinich, Panos M. Pardalos, and Marcello Pelillo.
   *The maximum clique problem*. In *Handbook of Combinatorial Optimization*,
   pages 1--74. Springer, 1999.
.. [5] Jan Karel Lenstra, A. H. G. Rinnooy Kan, and Peter Brucker.
   *Complexity of machine scheduling problems*. *Annals of Discrete
   Mathematics*, 1:343--362, 1977.
