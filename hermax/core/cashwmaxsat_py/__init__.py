from .cashwmaxsat_solver import CASHWMaxSATSolver
try:
    from ..cashwmaxsat import CASHWMaxSAT
except ImportError:
    # This might happen during build or if not compiled
    pass
