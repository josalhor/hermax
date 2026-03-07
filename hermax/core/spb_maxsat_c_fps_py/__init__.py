from .spb_maxsat_c_fps_solver import SPBMaxSATCFPSSolver
from .spb_maxsat_c_fps_reentrant import SPBMaxSATCFPSReentrant

try:
    from ..spb_maxsat_c_fps import SPBMaxSATCFPS  # native module class
except ImportError:
    pass

