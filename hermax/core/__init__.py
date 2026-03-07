"""
Core Hermax solver exports.

This module uses lazy attribute loading so importing `hermax.core` does not
require all native backends to load eagerly.
"""

import ctypes
from importlib import import_module
from pathlib import Path
import sys


def _preload_gmp_runtime_deps() -> None:
    # Best-effort preload for auditwheel-style vendored GMP names.
    # Needed when native modules link to hashed sonames (e.g. libgmp-*.so).
    suffixes = ("hermax.libs", "pymaxsat.libs")
    bases: list[Path] = []

    here = Path(__file__).resolve()
    bases.append(here.parents[2])  # site-packages root when installed
    bases.extend(Path(p) for p in sys.path if p)

    seen: set[Path] = set()
    dirs: list[Path] = []
    for base in bases:
        for suffix in suffixes:
            d = base / suffix
            if d.is_dir() and d not in seen:
                seen.add(d)
                dirs.append(d)

    if not dirs:
        return

    if sys.platform.startswith("linux"):
        patterns = ("libgmp*.so*", "libgmpxx*.so*")
        mode = getattr(ctypes, "RTLD_GLOBAL", 0)
    elif sys.platform == "darwin":
        patterns = ("libgmp*.dylib", "libgmpxx*.dylib")
        mode = getattr(ctypes, "RTLD_GLOBAL", 0)
    else:
        patterns = ("libgmp*.dll", "gmp*.dll")
        mode = 0

    for d in dirs:
        for pat in patterns:
            for lib in sorted(d.glob(pat)):
                try:
                    ctypes.CDLL(str(lib), mode=mode)
                except OSError:
                    pass


_preload_gmp_runtime_deps()

_EXPORTS = {
    "UWrMaxSATSolver": (".uwrmaxsat_py", "UWrMaxSATSolver"),
    "UWrMaxSATCompSolver": (".uwrmaxsat_comp_py", "UWrMaxSATCompSolver"),
    "UWrMaxSATCompReentrant": (".uwrmaxsat_comp_py", "UWrMaxSATCompReentrant"),
    "CASHWMaxSATSolver": (".cashwmaxsat_py", "CASHWMaxSATSolver"),
    "EvalMaxSATLatestSolver": (".evalmaxsat_latest_py", "EvalMaxSATLatestSolver"),
    "EvalMaxSATLatestReentrant": (".evalmaxsat_latest_py", "EvalMaxSATLatestReentrant"),
    "EvalMaxSATIncrSolver": (".evalmaxsat_incr_py", "EvalMaxSATIncrSolver"),
    "WMaxCDCLSolver": (".wmaxcdcl_py", "WMaxCDCLSolver"),
    "WMaxCDCLReentrant": (".wmaxcdcl_py", "WMaxCDCLReentrant"),
    "SPBMaxSATCFPSSolver": (".spb_maxsat_c_fps_py", "SPBMaxSATCFPSSolver"),
    "SPBMaxSATCFPSReentrant": (".spb_maxsat_c_fps_py", "SPBMaxSATCFPSReentrant"),
    "NuWLSCIBRSolver": (".nuwls_c_ibr_py", "NuWLSCIBRSolver"),
    "LoandraSolver": (".loandra_py", "LoandraSolver"),
    "RC2Reentrant": (".rc2", "RC2Reentrant"),
    "CGSSSolver": (".cgss_py", "CGSSSolver"),
    "CGSSPMRESSolver": (".cgss_py", "CGSSPMRESSolver"),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str):
    try:
        mod_name, attr = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    mod = import_module(mod_name, __name__)
    value = getattr(mod, attr)
    globals()[name] = value
    return value
