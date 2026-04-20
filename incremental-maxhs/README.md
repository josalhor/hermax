iMaxHS
======

This is an incremental version of the MaxSAT solver [MaxHS](http://maxhs.org), developed as an extension of the [MaxSAT Evaluation 2021 version](https://maxsat-evaluations.github.io/2021/mse21-solver-src/complete/maxhs.zip) of the solver. MaxHS is based on the implicit hitting set approach, and makes use of the SAT solver [CaDiCaL](https://github.com/arminbiere/cadical) and the MIP solver [IBM CPLEX Optimizer](https://www.ibm.com/analytics/cplex-optimizer).

For more information on iMaxHS, see the following papers. Please also remember to add citations when using Incremental MaxHS in your work.

Andreas Niskanen, Jeremias Berg, and Matti Järvisalo. [Incremental Maximum Satisfiability.](https://www.cs.helsinki.fi/u/andreasn/papers/niskanenbj-sat2022.pdf) In *Proceedings of the 25th International Conference on Theory and Applications of Satisfiability Testing (SAT 2022)*, volume 236 of LIPIcs. Schloss Dagstuhl – Leibniz-Zentrum für Informatik, 2022. To appear.

Andreas Niskanen, Jeremias Berg, and Matti Järvisalo. [Enabling Incrementality in the Implicit Hitting Set Approach to MaxSAT under Changing Weights.](https://drops.dagstuhl.de/opus/volltexte/2021/15335/) In *Proceedings of the 27th International Conference on Principles and Practice of Constraint Programming (CP 2021)*, pages 44:1-44:19, volume 210 of LIPIcs. Schloss Dagstuhl – Leibniz-Zentrum für Informatik, 2021.

Features
--------

iMaxHS fully supports the [IPAMIR specification](https://bitbucket.org/coreo-group/ipamir/) for incremental MaxSAT. This includes addition of hard clauses, soft literals, changing weights, and assumptions. See the SAT 2022 paper and the [MaxSAT Evaluation 2022 Incremental Track](https://maxsat-evaluations.github.io/2022/incremental.html) description for more details on IPAMIR.

Installation
------------

1. Download and install CPLEX on your machine. Note that it is available for free for students and researchers via the [IBM Academic Initiative](https://www.ibm.com/academic/home).

2. Modify the Makefile variables `LINUX_CPLEXLIBDIR` and `LINUX_CPLEXINCDIR` in `src/Makefile`. `LINUX_CPLEXLIBDIR` is the path containing the static library `libcplex.a`, and `LINUX_CPLEXINCDIR` is the path containing the directory `ilcplex`, which in turn contains the CPLEX headers. If compiling on macOS, modify `DARWIN_CPLEXLIBDIR` and `DARWIN_CPLEXINCDIR` instead.

3. Compile MaxHS by issuing `make` in the `src` directory.

4. Build the IPAMIR static library by issuing `make ipamir` in the `src` directory. The static library will be available as `src/build/release/lib/libipamirmaxhs.a`.
For building an IPAMIR application, include the `ipamir.h` header, and provide the linker with the following flags:
```
-lipamirmaxhs -L$(IPAMIRLIBDIR) -lz -L$(LINUX_CPLEXLIBDIR) -lcplex -lpthread -ldl
```
Here `IPAMIRLIBDIR` is the location of `libipamirmaxhs.a`, and `LINUX_CPLEXLIBDIR` is the location of the CPLEX library.
