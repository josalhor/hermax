Examples
========

All examples below are executable Python files in ``examples/``.

Modelling Gallery
------------------

For an introduction of the modelling examples 
(problem, new primitives, model, code, and output), see:

* :doc:`model_examples`

For a gallery focused on optimization modelling tricks
(piecewise costs, binning, ladder constraints, fast paths,
interval makespan, and ``all_different`` backends), see:

* :doc:`model_examples_tricks`

For a small gallery of classic NP-hard problems, see:

* :doc:`np_problems`

Soft-cost polarity note
-----------------------

Hermax examples use two closely related, but easy-to-confuse, APIs for soft
constraints:

* IPAMIR soft literals (``set_soft(lit, w)`` / ``add_soft_unit(lit, w)``):
  the cost is paid when the **literal is false**. For example,
  ``set_soft(-x, 5)`` means paying ``5`` when ``x=True``.
* WCNF soft clauses (``WCNF.append(clause, weight=...)``):
  the cost is paid when the **clause is violated**. For a unit clause
  ``[x]``, that means paying when ``x=False``.


.. _example-cvrp:

CVRP
----

This is a capacitated vehicle routing (CVRP) example with depot-to-customer
routes, capacity tracking, and MTZ load constraints [5]_.

Related API: :class:`hermax.model.Model`.

Problem
^^^^^^^^^^^^^^^^^^^^

.. only:: html

   .. image:: _static/cvrp_flat_problem.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (cvrp problem). See the HTML docs for the diagram.*

.. literalinclude:: ../examples/cvrp_flat.py
   :language: python
   :caption: examples/cvrp_flat.py

Output
^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: _generated/example_outputs/cvrp_flat.txt
   :language: console

Solution
^^^^^^^^^^^^^^^^

.. only:: html

   .. image:: _static/cvrp_flat_solution.svg
      :class: cvrp-problem-view

.. only:: latex

   *Visualization omitted from PDF build (cvrp solution). See the HTML docs for the diagram.*


Incremental MaxSAT
----------------------

Below is the smallest Hermax workflow with Incremental MaxSAT: add hard
constraints, assign soft penalties, update a soft weight (last write wins), and
solve under assumptions. This is the mental model for the IPAMIR
API used across the library, using UWrMaxSAT [1]_.

Related API: :class:`hermax.incremental.UWrMaxSAT`.

.. literalinclude:: ../examples/quickstart_uwrmaxsat.py
   :language: python
   :caption: examples/quickstart_uwrmaxsat.py

Output
^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: _generated/example_outputs/quickstart_uwrmaxsat.txt
   :language: console

RC2
---------------------------------------

Use this if you already have formulas in PySAT's ``WCNF`` format and want to
run them through Hermax without rewriting your formula-building code. It also
shows the non-incremental/rebuild wrapper style, which keeps the same API but
is a better fit for one-time solves than repeated incremental queries. This
example uses PySAT's ``WCNF`` representation [3]_ together with RC2 [2]_.

Related API: :class:`hermax.non_incremental.RC2`, :doc:`rc2`.

.. literalinclude:: ../examples/non_incremental_rc2_reentrant.py
   :language: python
   :caption: examples/non_incremental_rc2_reentrant.py

Output
^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: _generated/example_outputs/non_incremental_rc2_reentrant.txt
   :language: console

Load from WCNF Formula
----------------------

Use this constructor path when your formula is already built elsewhere 
and you want to hand the whole WCNF to a solver instead of 
replaying clause additions manually. This is useful when the formula
already comes from a PySAT-based workflow [3]_.

Related API: :class:`hermax.incremental.EvalMaxSAT`.

.. literalinclude:: ../examples/load_wcnf_formula.py
   :language: python
   :caption: examples/load_wcnf_formula.py

Output
^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: _generated/example_outputs/load_wcnf_formula.txt
   :language: console

OptiLog Compatibility
------------------------------

Use this when pipelines produce OptiLog formulas and need to solve
them in Hermax without rewriting them into PySAT. This example is specifically
about OptiLog interoperability [4]_.

Related API: :class:`hermax.incremental.UWrMaxSAT`.
External docs: `OptiLog documentation <https://hardlog.udl.cat/static/doc/optilog/html/index.html>`_.

OptiLog has **its own licensing model** and is an optional dependency of Hermax.

.. literalinclude:: ../examples/optilog_formula_compat.py
   :language: python
   :caption: examples/optilog_formula_compat.py

Output
^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: _generated/example_outputs/optilog_formula_compat.txt
   :language: console

Custom Portfolio
--------------------------------------

Use this when a portfolio is needed: combine a complete solver with a
fast incomplete solver, run both in isolated processes, and let the portfolio
return the first optimal result, or the best valid result before timeout otherwhise.

Related API: :class:`hermax.portfolio.PortfolioSolver`, :doc:`portfolio`.

.. literalinclude:: ../examples/portfolio_mixed.py
   :language: python
   :caption: examples/portfolio_mixed.py

Output
^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: _generated/example_outputs/portfolio_mixed.txt
   :language: console

Default Portfolios
-------------------------------

Use this when solver lists are not curated by hand. The preset
constructors auto-discover backends from Hermax namespaces and build:

* A complete-only portfolio, or
* A mixed performance portfolio

This is the fastest way to get a performance boost.

Related API: :class:`hermax.portfolio.CompletePortfolioSolver`,
:class:`hermax.portfolio.PerformancePortfolioSolver`, :doc:`portfolio`.

.. literalinclude:: ../examples/portfolio_presets.py
   :language: python
   :caption: examples/portfolio_presets.py

Output
^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: _generated/example_outputs/portfolio_presets.txt
   :language: console

References
----------
.. [1] Marek Piotrów. *UWrMaxSat: Efficient Solver for MaxSAT and
   Pseudo-Boolean Problems*. ICTAI 2020.
.. [2] Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva.
   *RC2: An Efficient MaxSAT Solver*. JSAT 11(1), 2019.
.. [3] Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva.
   *PySAT: A Python Toolkit for Prototyping with SAT Oracles*. SAT 2018.
.. [4] Carlos Ansótegui, Jesus Ojeda, António Pacheco, Josep Pon,
   Josep M. Salvia, Eduard Torres.
   *Optilog: A framework for SAT-based systems*. SAT 2021.
.. [5] Clair E. Miller, Albert W. Tucker, Richard A. Zemlin.
   *Integer programming formulation of traveling salesman problems*.
   *Journal of the ACM*, 7(4):326--329, 1960.
