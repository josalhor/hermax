.. hermax documentation master file

.. image:: ../images/banner.png
   :align: center
   :alt: Hermax Logo
   :class: hero-banner

Hermax: MaxSAT Optimization for Python
=============================================

.. image:: https://img.shields.io/pypi/v/hermax.svg
   :target: https://pypi.org/project/hermax/
   :alt: PyPI version

.. image:: https://img.shields.io/pypi/wheel/hermax.svg
   :target: https://pypi.org/project/hermax/
   :alt: PyPI wheel

.. image:: https://img.shields.io/pypi/pyversions/hermax.svg
   :target: https://pypi.org/project/hermax/
   :alt: Python versions

.. image:: https://img.shields.io/badge/License-Apache%202.0-blue.svg
   :target: https://github.com/josalhor/hermax/blob/main/LICENSE
   :alt: License Apache-2.0

.. image:: https://readthedocs.org/projects/hermax/badge/?version=latest
   :target: https://hermax.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

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
black-box CP approach, CP-SAT or MiniZinc may also be a good alternative.

Hermax is especially relevant for:

* engineers building reliable (mostly boolean) optimization problems
* users who already work with clauses, WCNF, or incremental solver APIs
* researchers comparing MaxSAT backends behind a common Python interface

Start Here
----------

* :doc:`quickstart` if you want the fastest path to a working Hermax model and a direct solver example.
* :doc:`examples` if you want solver examples such as UWrMaxSAT, RC2, graph colouring, scheduling, and CVRP.
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
