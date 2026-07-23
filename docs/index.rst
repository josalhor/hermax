.. hermax documentation master file

.. image:: ../images/banner.png
   :align: center
   :alt: Hermax Logo
   :class: hero-banner

Hermax: MaxSAT Optimization for Python
=============================================

.. raw:: html

   <p align="center">
     <a href="https://pypi.org/project/hermax/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/hermax.svg"></a>
     <a href="https://pypi.org/project/hermax/"><img alt="PyPI wheel" src="https://img.shields.io/pypi/wheel/hermax.svg"></a>
     <a href="https://pypi.org/project/hermax/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/hermax.svg"></a>
     <a href="https://github.com/josalhor/hermax/blob/main/LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/License-Apache%202.0-blue.svg"></a>
     <a href="https://hermax.readthedocs.io/en/latest/?badge=latest"><img alt="Documentation Status" src="https://readthedocs.org/projects/hermax/badge/?version=latest"></a>
     <br>
     <a href="https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2026.41"><img alt="Paper: SAT 2026" src="https://img.shields.io/badge/Paper-SAT%202026-007C7A"></a>
     <img alt="Windows supported" src="https://img.shields.io/badge/Windows-supported-0078D6?logo=windows">
     <img alt="Linux supported" src="https://img.shields.io/badge/Linux-supported-FCC624?logo=linux&amp;logoColor=black">
     <img alt="macOS supported" src="https://img.shields.io/badge/macOS-supported-000000?logo=apple">
   </p>

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
