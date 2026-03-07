"""
Hermax: A Python library of incremental MaxSAT solvers.

This package intentionally avoids eager importing backend-heavy modules at
import time so optional/native dependencies can fail independently.
"""

from importlib import import_module

__all__ = ["incremental", "non_incremental", "portfolio", "utils"]


def __getattr__(name: str):
    if name in __all__:
        mod = import_module(f".{name}", __name__)
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
