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
* :doc:`changelog` for versioned user-facing changes.

Citation
--------

If you use Hermax in research, please cite:

.. code-block:: bibtex

   @InProceedings{salviahornos_et_al:LIPIcs.SAT.2026.41,
     author = {Salvia Hornos, Josep Maria and Fern\'{a}ndez Cam\'{o}n, C\`{e}sar and Mateu Pi\~{n}ol, Carles},
     title = {{Hermax: A Unified MaxSAT Library}},
     booktitle = {29th International Conference on Theory and Applications of Satisfiability Testing (SAT 2026)},
     pages = {41:1--41:13},
     series = {Leibniz International Proceedings in Informatics (LIPIcs)},
     ISBN = {978-3-95977-431-4},
     ISSN = {1868-8969},
     year = {2026},
     volume = {377},
     editor = {Ignatiev, Alexey and Szeider, Stefan},
     publisher = {Schloss Dagstuhl -- Leibniz-Zentrum f\"{u}r Informatik},
     address = {Dagstuhl, Germany},
     URL = {https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2026.41},
     URN = {urn:nbn:de:0030-drops-263478},
     doi = {10.4230/LIPIcs.SAT.2026.41},
     annote = {Keywords: MaxSAT, Incremental Solving, IPAMIR, Python, Constraint modelling}
   }

See :doc:`Acknowledgments <acknowledgments>` for backend solver citations and
other project references.

.. toctree::
   :hidden:
   :maxdepth: 2

   quickstart
   examples
   modeling
   API <api>
   changelog
   Developer <developer>
   Citation <acknowledgments>
