### README for the TT-Open-WBO-Inc MaxSAT Solver

TT-Open-WBO-Inc is an anytime MaxSAT solver. It's a spin-off of Open-WBO-Inc. 

Author: Alexander Nadel, alexandernad@technion.ac.il
Authors and contributors of the baseline solver Open-WBO-Inc: Ruben Martins, Vasco Manquinho, Ines Lynce, Miguel Neves, Saurabh Joshi, Mikolas Janota
Authors of the local search solver NuWLS-c: Yi Chu, Shaowei Cai, Zhendong Lei, Xiang He

### Version TT-Open-WBO-Inc-24 -- MaxSAT Evaluation 2024

*We used gcc 10.1 to compile.*

We have submitted 2 versions of the solver (with two different underlying SAT solvers -- Intel(R) SAT Solver and Glucose). Compiling instructions for each:

1) TT-Open-WBO-Inc-24(I) : 

Make sure that the following lines are uncommented in Makefile:

	SOLVERNAME = "IntelSATSolver"
	SOLVERDIR  = topor
	NSPACE     = ToporWrapper

To compile (use "make d" for Debug mode, and "make" for Release with debug infomation):

	make rs

To run:

	tt-open-wbo-inc-IntelSATSolver_static <INSTANCE>

2) TT-Open-WBO-Inc-24(G) : 

Make sure that the following lines are uncommented in Makefile:

	SOLVERNAME = "Glucose4_1"
	SOLVERDIR  = glucose4.1
	NSPACE     = Glucose

To compile (use "make d" for Debug mode, and "make" for Release with debug infomation):

	make rs

To run:

	tt-open-wbo-inc-Glucose4_1_static <INSTANCE>
