from .wmaxcdcl_solver import WMaxCDCLSolver
from .wmaxcdcl_reentrant import WMaxCDCLReentrant

try:
    from ..wmaxcdcl import WMaxCDCL  # native pybind module
except ImportError:
    pass

