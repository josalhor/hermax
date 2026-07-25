"""
A Python interface for Aperture.

Aperture is a SAT-based optimization tool with support for:
- SAT solving under assumptions
- MaxSAT (weighted/unweighted) with anytime & incremental solving
- OBV (Modulo Bit-Vector Optimization)
- Black-box optimization
- Constraint encoding (cardinality, pseudo-Boolean)
"""

try:
    from . import _aperture
except ImportError as e:
    raise ImportError(
        "Failed to import the native aperture module. "
        "Make sure aperture is properly installed. "
        f"Original error: {e}"
    ) from e

from .__version__ import __version__

# Expose the main Solver class
Solver = _aperture.Solver
lits = _aperture.lits
wlits = _aperture.wlits

__all__ = [
    "Solver",
    "lits",
    "wlits",
    "__version__",
]
