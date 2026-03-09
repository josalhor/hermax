.. hermax documentation master file

.. image:: ../images/banner.png
   :align: center
   :alt: Hermax Logo
   :class: hero-banner

Hermax: MaxSAT Optimization for Python
=============================================

**Hermax** is a pormanteau of **Hermes** and **MaxSAT**. 

In Greek mythology, Hermes is the messenger between the worlds of gods and mortals. 
Similarly, Hermax is conceived as the bridge between Python, the divine world where messages are sent down the stack, 
and C/C++, the mortal world with it's struggles and hardships, where performance is critical.

Who Is This For?
----------------

Hermax is for combinatorially hard problems where:

* finding even a good base solution is already difficult
* the search state is mostly boolean

This is usually a better fit than MILP tooling when your problem is not mainly
about floating-point structure, large integer arithmetic, or strong LP
relaxations. In those cases, a MILP such as PuLP, SCIP, or Gurobi is
often the more natural first choice.

If your problem is highly combinatorial but can benefit from a broader
black-box CP approach, CP-SAT may also be a good alternative.

Hermax is especially relevant for:

* engineers building repeated optimization workflows around hard clauses, soft
  literals, assumptions, and iterative solve loops,
* users who already work with clauses, WCNF, or incremental solver-style APIs,
  and
* researchers comparing MaxSAT backends behind a common Python interface.

Start Here
----------

* :doc:`quickstart` if you want the fastest path to a working Hermax model and a direct solver example.
* :doc:`examples` if you want solver-oriented examples such as UWrMaxSAT, RC2, graph colouring, scheduling, and CVRP.
* :doc:`modeling` if you want the modelling compiler, runnable examples, and advanced modelling tricks.

Useful Next Steps
-----------------

* :doc:`portfolio` for multi-solver execution and preset portfolios.
* :doc:`incremental` for incremental MaxSAT workflows and assumptions.
* :doc:`bindings` for backend-specific notes and solver availability.
* :doc:`api` if you want the full API reference.

.. toctree::
   :hidden:
   :maxdepth: 2

   quickstart
   examples
   modeling
   api
   developer
