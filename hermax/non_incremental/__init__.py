"""
This module provides access to solvers that do not natively support the
IPAMIR incremental interface. They are wrapped in a re-encoding layer
that rebuilds the problem for each solve call, providing compatibility
with the IPAMIR interface at the cost of some performance in incremental
scenarios.
"""
from hermax.core.rc2 import RC2Reentrant
from hermax.core.uwrmaxsat_comp_py import UWrMaxSATCompReentrant
from hermax.core.evalmaxsat_latest_py import EvalMaxSATLatestReentrant
from hermax.core.evalmaxsat_incr_py import EvalMaxSATIncrSolver
from hermax.core.cashwmaxsat_py import CASHWMaxSATSolver
from hermax.core.cgss_py import CGSSSolver, CGSSPMRESSolver
from hermax.core.openwbo_py import OLLSolver, PartMSU3Solver, AutoOpenWBOSolver
from hermax.core.wmaxcdcl_py import WMaxCDCLReentrant

class RC2(RC2Reentrant):
    """
    RC2: A powerful MaxSAT solver based on the RC2 algorithm, 
    using the PySAT implementation. This version is reentrant 
    and suitable for non-native incremental use.
    """
    pass

class UWrMaxSATCompetition(UWrMaxSATCompReentrant):
    """
    UWrMaxSAT (Competition version): A reentrant wrapper for the 
    competition version 1.4.
    """
    pass

class EvalMaxSAT(EvalMaxSATLatestReentrant):
    """
    EvalMaxSAT: Latest version of EvalMaxSAT, wrapped for 
    reentrant incremental use.
    """
    pass

class CASHWMaxSAT(CASHWMaxSATSolver):
    """
    CASHWMaxSAT: An award-winning hybrid MaxSAT solver
    """
    pass

# class CASHWMaxSATNoSCIP(CASHWMaxSAT):
#     """
#     CASHWMaxSAT (without SCIP): CASHWMaxSAT with SCIP disabled.
#     """
#     def __init__(self, formula=None, **kwargs):
#         super().__init__(formula, disable_scip=True, **kwargs)


if WMaxCDCLReentrant is not None:
    class WMaxCDCL(WMaxCDCLReentrant):
        """
        WMaxCDCL: branch-and-bound + clause learning MaxSAT solver (rebuild wrapper).
        """
        pass
else:
    class WMaxCDCL:  # pragma: no cover - import-time fallback
        def __init__(self, *args, **kwargs):
            raise RuntimeError("WMaxCDCL native module is not available in this environment.")


class CGSS(CGSSSolver):
    """
    CGSS complete solver (RC2WCE + structure sharing + WCE), rebuild wrapper.
    """
    pass


class CGSSPMRES(CGSSPMRESSolver):
    """
    CGSS PMRES variant, rebuild wrapper.
    """
    pass


class OpenWBOOLL(OLLSolver):
    """
    Open-WBO OLL algorithm (rebuild wrapper).
    """
    pass


class OpenWBOPartMSU3(PartMSU3Solver):
    """
    Open-WBO PartMSU3 algorithm (rebuild wrapper).
    """
    pass


class OpenWBO(AutoOpenWBOSolver):
    """
    Open-WBO auto mode (rebuild wrapper): routes to OLL/PartMSU3/MSU3.
    """
    pass

UWrMaxSATComp = UWrMaxSATCompetition
OpenWBOAuto = OpenWBO

__all__ = [
    "RC2",
    # "UWrMaxSATCompetition",
    "EvalMaxSAT",
    "EvalMaxSATIncrSolver",
    "CASHWMaxSAT",
    # "CASHWMaxSATNoSCIP",
    "WMaxCDCL",
    "CGSS",
    "CGSSPMRES",
    "OpenWBOOLL",
    "OpenWBOPartMSU3",
    "OpenWBO",
    # "UWrMaxSATComp",
    # "OpenWBOAuto",
]
