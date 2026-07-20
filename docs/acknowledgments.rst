Acknowledgments
===============

We thank Alexey Ignatiev and Joao Marques-Silva for their participation in
related MaxSAT research discussions, and Elena Barrachina for reviewing parts
of the Hermax documentation.


Citing Hermax
-------------

If you use Hermax in research, cite the following paper:

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

Solver References
-------------------------------

Hermax builds on, integrates with, or is influenced by a broader SAT/MaxSAT and
optimization ecosystem. Relevant references include:

SAT Solvers
-----------

Selected SAT solver references used across the wider ecosystem include
Glucose [1]_, CaDiCaL [2]_, MiniSat [3]_, and CominiSatPS [4]_.

.. [1] Gilles Audemard and Laurent Simon. *On the glucose SAT solver*.
   International Journal on Artificial Intelligence Tools, 27(01):1840001, 2018.
.. [2] Armin Biere, Tobias Faller, Katalin Fazekas, Mathias Fleury,
   Nils Froleyks, and Florian Pollitt. *CaDiCaL 2.0*.
   International Conference on Computer Aided Verification, pages 133-152, 2024.
.. [3] Niklas Sorensson and Niklas Een.
   *Minisat v1.13 - a SAT solver with conflict-clause minimization*.
   SAT, 53:1-2, 2005.
.. [4] Chanseok Oh. *COMiniSatPS Pulsar and GHackCOMSPS*.
   In Tomas Balyo, Marijn J. H. Heule, and Matti Jarvisalo (eds.),
   *Proceedings of SAT Competition 2017: Solver and Benchmark Descriptions*,
   volume B-2017-1, pages 12-13, 2017. Department of Computer Science,
   University of Helsinki.

Python and SAT References
----------------------

* Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva.
  *PySAT: A Python Toolkit for Prototyping with SAT Oracles*. SAT 2018.
* Carlos Ansotegui, Jesus Ojeda, Antonio Pacheco, Josep Pon, Josep M. Salvia,
  Eduard Torres.
  *Optilog: A framework for SAT-based systems*. SAT 2021.
* Josep Alos, Carlos Ansotegui, Josep M. Salvia, Eduard Torres.
  *Optilog V2: model, solve, tune and run*. SAT 2022.
* Tias Guns.
  *Increasing modeling language convenience with a universal n-dimensional array, CPpy as python-embedded example*.
  Proceedings of the 18th workshop on Constraint Modelling and Reformulation at CP (ModRef 2019), volume 19, 2019.
* Nicholas Nethercote, Peter J. Stuckey, Ralph Becket, Sebastian Brand,
  Gregory J. Duck, Guido Tack.
  *MiniZinc: Towards a standard CP modelling language*.
  International Conference on Principles and Practice of Constraint Programming, pages 529-543, 2007.
* J. S. Roy, Stuart A. Mitchell, and PuLP contributors.
  *PuLP*, version 3.3.0, 2025.
  https://pypi.org/project/PuLP/


MaxSAT References
-----------------

The following MaxSAT-focused academic references are currently cited across the
Hermax documentation set:

* Andreas Niskanen, Jeremias Berg, Matti Järvisalo.
  *Incremental Maximum Satisfiability*. SAT 2022.
* Marek Piotrów.
  *UWrMaxSat: Efficient Solver for MaxSAT and Pseudo-Boolean Problems*.
  ICTAI 2020.
* Florent Avellaneda.
  *EvalMaxSAT*. MaxSAT Evaluation: Solver and Benchmark Descriptions, 2023.
* Alexey Ignatiev, Antonio Morgado, Joao Marques-Silva.
  *RC2: An Efficient MaxSAT Solver*. JSAT 11(1), 2019.
* Hannes Ihalainen, Jeremias Berg, Matti Järvisalo.
  *Refined Core Relaxation for Core-Guided MaxSAT Solving*. CP 2021.
* Jeremias Berg, Bart Bogaerts, Jakob Nordström, Andy Oertel,
  Dieter Vandesande.
  *Certified Core-Guided MaxSAT Solving*. CADE 29, 2023.
* Ruben Martins, Vasco Manquinho, Ines Lynce.
  *Open-WBO: A Modular MaxSAT Solver*. SAT 2014.
* Benjamin Andres, Benjamin Kaufmann, Oliver Matheis, Torsten Schaub.
  *Unsatisfiability-based Optimization in clasp*. ICLP 2012 Technical
  Communications.
* Saurabh Joshi, Prateek Kumar, Sukrut Rao, Ruben Martins.
  *Open-WBO-Inc: Approximation Strategies for Incomplete Weighted MaxSAT*.
  Journal on Satisfiability, Boolean Modelling and Computation 11(1), 2019.
* Shiwei Pan, Yiyuan Wang, Shaowei Cai.
  *An Efficient Core-Guided Solver for Weighted Partial MaxSAT*. IJCAI 2025.
* Mingming Jin, Kun He, Jiongzhi Zheng, Jinghui Xue, Zhuo Chen.
  *Combining BandMaxSAT and FPS with SPB-MaxSAT-c*.
  MaxSAT Evaluation 2024: Solver and Benchmark Descriptions, 2024.
* Menghua Jiang.
  *NuWLS-c-IBR*. MaxSAT Evaluation solver description, 2023.
* Jeremias Berg, Emir Demirovic, Peter J. Stuckey.
  *Core-Boosted Linear Search for Incomplete MaxSAT*. CPAIOR 2019.
* Xujie Si, Xin Zhang, Vasco Manquinho, Mikolás Janota, Alexey Ignatiev,
  Mayur Naik.
  *On Incremental Core-Guided MaxSAT Solving*. CP 2016.
* Alexey Ignatiev, Yacine Izza, Peter J. Stuckey, Joao Marques-Silva.
  *Using MaxSAT for Efficient Explanations of Tree Ensembles*. AAAI 2022.
* Tobias Paxian, Armin Biere.
  *MaxSAT Fuzzing and Delta Debugging*. Journal of Artificial Intelligence
  Research, 85, 2026.
* Andreas Niskanen, Jeremias Berg, Matti Järvisalo. *Enabling Incrementality in the Implicit Hitting Set Approach to MaxSAT Under Changing Weights*. CP 2021.
* Jessica Davies. *Solving MaxSAT by Decoupling Optimization and Satisfaction*. Doctoral dissertation, 2014.
