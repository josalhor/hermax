Basic Usage
===========

.. quickstart-basic-body-start

Start with the modelling path. This is the entry point if your
problem is already expressed in terms of decisions, constraints, and an
objective.

Model Example
-------------

This CVRP example shows the usual Hermax workflow with MTZ load
constraints [1]_:

1. declare variables,
2. add hard constraints,
3. add soft costs,
4. solve and inspect the selected decisions.

Problem
^^^^^^^

.. only:: html

   .. image:: _static/cvrp_flat_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (cvrp problem). See the HTML docs for the diagram.*

.. literalinclude:: ../examples/cvrp_flat.py
   :language: python
   :caption: examples/cvrp_flat.py

Output
^^^^^^

.. literalinclude:: _generated/example_outputs/cvrp_flat.txt
   :language: text
   :caption: Model example output

Solution
^^^^^^^^

.. only:: html

   .. image:: _static/cvrp_flat_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (cvrp solution). See the HTML docs for the diagram.*

Incremental MaxSAT Example
--------------------------

If you already work with literals and clauses, use the solver API
without going through the modelling layer. This version uses
``pysat.formula.IDPool`` from PySAT [2]_ to manage variable identifiers and
``hermax.incremental.UWrMaxSAT`` [3]_ as the backend.

.. literalinclude:: ../examples/quickstart_uwrmaxsat.py
   :language: python
   :caption: examples/quickstart_uwrmaxsat.py

Output
^^^^^^

.. literalinclude:: _generated/example_outputs/quickstart_uwrmaxsat.txt
   :language: text
   :caption: Direct solver example output

References
----------

.. [1] Clair E. Miller, Albert W. Tucker, Richard A. Zemlin.
   *Integer programming formulation of traveling salesman problems*.
   *Journal of the ACM*, 7(4):326--329, 1960.
.. [2] Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva.
   *PySAT: A Python Toolkit for Prototyping with SAT Oracles*. SAT 2018.
.. [3] Marek Piotrów. *UWrMaxSat: Efficient Solver for MaxSAT and
   Pseudo-Boolean Problems*. ICTAI 2020.

.. quickstart-basic-body-end
