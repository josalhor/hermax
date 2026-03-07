"""
This module provides access to solvers that natively support the IPAMIR
incremental MaxSAT interface. These solvers are generally more efficient
for sequences of related MaxSAT queries as they maintain internal state
between solve calls.
"""
from hermax.core.uwrmaxsat_py import UWrMaxSATSolver
from hermax.core.uwrmaxsat_comp_py import UWrMaxSATCompSolver
from hermax.core.evalmaxsat_latest_py import EvalMaxSATLatestSolver
from hermax.core.evalmaxsat_incr_py import EvalMaxSATIncrSolver

class UWrMaxSAT(UWrMaxSATSolver):
    """
    UWrMaxSAT: an efficient MaxSAT solver based on the UWrMaxSAT 1.8 solver.
    This solver provides native incremental support through the IPAMIR interface.

    UWrMaxSAT is known for its efficiency in handling various MaxSAT instances, 
    combining modern SAT solving techniques with effective MaxSAT algorithms.
    """
    pass

class UWrMaxSATCompetition(UWrMaxSATCompSolver):
    """
    UWrMaxSAT (Competition version): A highly efficient MaxSAT solver, 
    specifically the version 1.4 used in competitions.
    This solver provides native incremental support through the IPAMIR interface.

    It is particularly optimized for competition-style benchmarks and 
    provides robust performance across a wide range of MaxSAT problems.
    """
    pass

class EvalMaxSAT(EvalMaxSATLatestSolver):
    """
    EvalMaxSAT: Latest version of EvalMaxSAT with native IPAMIR support.
    
    EvalMaxSAT is a state-of-the-art solver known for its performance 
    in MaxSAT competitions.
    """
    pass

class EvalMaxSATIncremental(EvalMaxSATIncrSolver):
    """
    EvalMaxSAT (Incremental): Specialized incremental version of EvalMaxSAT.
    """
    pass


# Backward-compatible aliases for historical public names.
UWrMaxSATComp = UWrMaxSATCompetition
EvalMaxSATIncr = EvalMaxSATIncremental

__all__ = [
    "UWrMaxSAT",
    "UWrMaxSATCompetition",
    "EvalMaxSAT",
    "EvalMaxSATIncremental",
    # "UWrMaxSATComp",
    # "EvalMaxSATIncr",
]
