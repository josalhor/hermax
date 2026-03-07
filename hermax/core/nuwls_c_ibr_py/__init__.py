from .nuwls_c_ibr_solver import NuWLSCIBRSolver
from .nuwls_c_ibr_subprocess import NuWLSCIBR

try:
    from ..nuwls_c_ibr import NuWLSCIBR as NuWLSCIBRNative
except ImportError:
    pass
