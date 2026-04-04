TT-Open-WBO-Inc: an anytime MaxSAT solver by Alexander Nadel. The solver has been developed since 2019, when it won both of the weighted incomplete categories at MaxSAT Evaluation 2019. 

Since then, different versions of TT-Open-WBO-Inc has been part of various award-winning solvers, including the winners of MaxSAT Evaluation 2023 and MaxSAT Evaluation 2024 in all four anytime categories (NuWLS-c-2023 and SPB-MaxSAT-c, respectively). 

TT-Open-WBO-Inc's GitHub version was initialized with the solver submitted to MaxSAT Evaluation 2023. 

TT-Open-WBO-Inc is described in the following two papers:

        "TT-Open-WBO-Inc: an Efficient Anytime MaxSAT Solver", Alexander Nadel, J. Satisf. Boolean Model. Comput. 15(1): 1-7 (2024)
        
        "Polarity and Variable Selection Heuristics for SAT-Based Anytime MaxSAT", Alexander Nadel, J. Satisf. Boolean Model. Comput. 12(1): 17-22 (2020)

The underlying algorithms are further detailed in:

        "Anytime Algorithms for MaxSAT and Beyond", Alexander Nadel, FMCAD'20 (tutorial)
  
        “On Optimizing a Generic Function in SAT”, Alexander Nadel, FMCAD'20.  
  
        “Anytime Weighted MaxSAT with Improved Polarity Selection and Bit-Vector Optimization”, Alexander Nadel, FMCAD'19.
  
        “Solving MaxSAT with Bit-Vector Optimization”, Alexander Nadel, SAT'18.

The license is MIT. See code/LICENSE for further details.

To compile, make sure that your g++ version is at least 10.1 and run:

        cd code
        make rs -j

To change the underlying SAT solver from IntelSAT to Glucose, edit code/Makefile as follows:

        #Glucose4_1
          
        SOLVERNAME = "Glucose4_1"
        SOLVERDIR  = glucose4.1
        NSPACE     = Glucose          
        
        #IntelSATSolver
        #SOLVERNAME = "IntelSATSolver"
        #SOLVERDIR  = topor
        #NSPACE     = ToporWrapper
  
