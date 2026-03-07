import os, sys

if sys.platform == "win32":
    os.environ["PATH"] = r"C:\msys64\mingw64\bin;" + os.environ.get("PATH", "")

import importlib
import os
import site
import sys
import tempfile
from pathlib import Path


def _norm(p: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(p))
    except Exception:
        return p


def _purge_paths_under(root: str):
    root_n = _norm(root)
    new = []
    removed = []
    for p in sys.path:
        if not p:
            continue
        pn = _norm(p)
        if pn == root_n or pn.startswith(root_n + os.sep):
            removed.append(p)
        else:
            new.append(p)
    sys.path[:] = new
    return removed


def _print_env():
    print("Python:", sys.executable)
    print("Version:", sys.version.replace("\n", " "))
    print("CWD:", os.getcwd())
    print("site-packages:")
    for sp in site.getsitepackages():
        print("  -", sp)
    usp = site.getusersitepackages()
    if usp:
        print("user-site:", usp)
    print("sys.path (first 10):")
    for i, p in enumerate(sys.path[:10]):
        print(f"  [{i}] {p}")


def test_import(name: str):
    print(f"\n== Import {name} ==")
    try:
        mod = importlib.import_module(name)
        where = getattr(mod, "__file__", "namespace/builtin")
        print("OK:", where)
        return mod
    except Exception as e:
        print("FAIL:", repr(e))
        raise


def assert_installed_binary(pkg_name: str, stem: str):
    """
    Ensure we have a compiled artifact for `stem` in the installed package dir.
    On Windows:  stem*.pyd
    On Linux:    stem*.so
    On macOS:    stem*.so or stem*.dylib (rare), plus .so for Python ext
    """
    pkg = importlib.import_module(pkg_name)
    pkg_dir = Path(pkg.__file__).resolve().parent
    print("\nInstalled package dir:", str(pkg_dir))

    patterns = [f"{stem}*.pyd", f"{stem}*.so", f"{stem}*.dylib", f"{stem}*.dll"]
    hits = []
    for pat in patterns:
        hits.extend(pkg_dir.glob(pat))

    if not hits:
        raise RuntimeError(
            f"Missing binary for {pkg_name}.{stem}. "
            f"Searched in {pkg_dir} for: {patterns}"
        )

    print(f"Found binary candidates for {stem}:")
    for h in hits:
        print("  -", h.name)


# ---- Main flow ----

# capture repo dir (where the smoke_test.py lives is better than cwd)
repo_dir = Path(__file__).resolve().parent
removed = _purge_paths_under(str(repo_dir))
os.chdir(tempfile.gettempdir())

_print_env()
if removed:
    print("\nRemoved paths under repo dir:")
    for p in removed:
        print("  -", p)

# First import the top-level package from the installed wheel
test_import("hermax")

# Verify the extension module files exist in installed package directory BEFORE importing them
# (This is exactly what your failure suggests: module missing from wheel.)
assert_installed_binary("hermax.core", "urmaxsat_py")
assert_installed_binary("hermax.core", "urmaxsat_comp_py")

# Then import submodules
modules = [
    "hermax.core.openwbo",
    "hermax.core.openwbo_inc",
    "hermax.core.evalmaxsat_incr",
    "hermax.core.evalmaxsat_latest",
    "hermax.core.urmaxsat_py",
    "hermax.core.urmaxsat_comp_py",
    "hermax.core.cashwmaxsat",
    "hermax.core.eval_py",
]
for m in modules:
    test_import(m)

# API surface sanity check
try:
    from hermax.non_incremental import EvalMaxSATIncrSolver
    print("\nOK: EvalMaxSATIncrSolver imported from hermax")
except Exception as e:
    raise RuntimeError("Failed to import EvalMaxSATIncrSolver") from e

print("\nALL SMOKE TESTS PASSED")
