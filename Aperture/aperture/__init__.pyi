"""
A Python interface for Aperture.

Aperture is a SAT-based optimization tool with support for:
- SAT solving under assumptions
- MaxSAT (weighted/unweighted) with anytime & incremental solving
- OBV (Modulo Bit-Vector Optimization)
- Black-box optimization
- Constraint encoding (cardinality, pseudo-Boolean)
"""

from ._aperture import Solver as Solver, lits as lits, wlits as wlits


__all__: list = ['Solver', 'lits', 'wlits', '__version__']
