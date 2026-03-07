"""
Incomplete (non-IPAMIR-native) MaxSAT solvers.

This subpackage contains wrappers around solvers that are either incomplete,
experimental, or otherwise not suitable for the main non-incremental solver
namespace yet.
"""

from hermax.core.openwbo_inc_py.openwbo_inc_subprocess import OpenWBOInc
from hermax.core.spb_maxsat_c_fps_py.spb_maxsat_c_fps_subprocess import SPBMaxSATCFPS
from hermax.core.nuwls_c_ibr_py.nuwls_c_ibr_subprocess import NuWLSCIBR
from hermax.core.loandra_py.loandra_subprocess import Loandra

__all__ = [
    "OpenWBOInc",
    "SPBMaxSATCFPS",
    "NuWLSCIBR",
    "Loandra",
]
