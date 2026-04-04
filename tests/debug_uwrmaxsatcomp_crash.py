#!/usr/bin/env python3
"""Systematic crash isolator for hermax.core.urmaxsat_comp_py.

Run from tests/ so the installed package is imported:
    cd tests && ../venv/bin/python debug_uwrmaxsatcomp_crash.py
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import textwrap


SCENARIOS = {
    "import_only": """
import faulthandler
faulthandler.enable()
print("[child] import start", flush=True)
import hermax.core.urmaxsat_comp_py as m
print(f"[child] import ok module={m.__file__}", flush=True)
""",
    "construct_only": """
import faulthandler
faulthandler.enable()
import hermax.core.urmaxsat_comp_py as m
print(f"[child] module={m.__file__}", flush=True)
print("[child] construct start", flush=True)
s = m.UWrMaxSAT()
print("[child] construct ok", flush=True)
""",
    "hard_only_solve": """
import faulthandler
faulthandler.enable()
import hermax.core.urmaxsat_comp_py as m
print(f"[child] module={m.__file__}", flush=True)
s = m.UWrMaxSAT()
print("[child] add hard [1]", flush=True)
s.addClause([1], None)
print("[child] solve start", flush=True)
r = s.solve()
print(f"[child] solve rc={r}", flush=True)
""",
    "hard_plus_soft_solve": """
import faulthandler
faulthandler.enable()
import hermax.core.urmaxsat_comp_py as m
print(f"[child] module={m.__file__}", flush=True)
s = m.UWrMaxSAT()
print("[child] add hard [1]", flush=True)
s.addClause([1], None)
print("[child] add soft [1] w=1", flush=True)
s.addClause([1], 1)
print("[child] solve start", flush=True)
r = s.solve()
print(f"[child] solve rc={r}", flush=True)
print(f"[child] cost={s.getCost()}", flush=True)
""",
    "hard_plus_zero_soft_solve": """
import faulthandler
faulthandler.enable()
import hermax.core.urmaxsat_comp_py as m
print(f"[child] module={m.__file__}", flush=True)
s = m.UWrMaxSAT()
print("[child] add hard [1]", flush=True)
s.addClause([1], None)
print("[child] add soft [1] w=0", flush=True)
s.addClause([1], 0)
print("[child] solve start", flush=True)
r = s.solve()
print(f"[child] solve rc={r}", flush=True)
""",
    "hard_plus_guard_pair_solve": """
import faulthandler
faulthandler.enable()
import hermax.core.urmaxsat_comp_py as m
print(f"[child] module={m.__file__}", flush=True)
s = m.UWrMaxSAT()
print("[child] add hard [1]", flush=True)
s.addClause([1], None)
print("[child] add guard hard [-2] + soft [-2] w=1", flush=True)
s.addClause([-2], None)
s.addClause([-2], 1)
print("[child] solve start", flush=True)
r = s.solve()
print(f"[child] solve rc={r}", flush=True)
print(f"[child] cost={s.getCost()}", flush=True)
print(f"[child] v1={s.getValue(1)} v2={s.getValue(2)}", flush=True)
""",
}


def run_scenario(name: str, python_exe: str) -> int:
    code = textwrap.dedent(SCENARIOS[name])
    print(f"\n=== scenario: {name} ===", flush=True)
    proc = subprocess.run([python_exe, "-c", code], text=True, capture_output=True)
    print(f"[parent] returncode={proc.returncode}", flush=True)
    if proc.stdout:
        print("[parent] stdout:", flush=True)
        print(proc.stdout, end="", flush=True)
    if proc.stderr:
        print("[parent] stderr:", flush=True)
        print(proc.stderr, end="", flush=True)
    return proc.returncode


def maybe_print_ldd(python_exe: str) -> None:
    # Optional Linux-only dynamic link snapshot for compilation-context debugging.
    if platform.system() != "Linux":
        return
    code = "import hermax.core.urmaxsat_comp_py as m; print(m.__file__)"
    proc = subprocess.run([python_exe, "-c", code], text=True, capture_output=True)
    if proc.returncode != 0:
        return
    so_path = proc.stdout.strip()
    if not so_path:
        return
    print(f"\n[module] {so_path}", flush=True)
    ldd = subprocess.run(["ldd", so_path], text=True, capture_output=True)
    print("[ldd]", flush=True)
    if ldd.stdout:
        print(ldd.stdout, end="", flush=True)
    if ldd.stderr:
        print(ldd.stderr, end="", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crash isolator for UWrMaxSATComp")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used for child scenario subprocesses",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIOS.keys()),
        help="scenario(s) to run; default runs all",
    )
    parser.add_argument("--skip-ldd", action="store_true", help="skip Linux ldd output")
    args = parser.parse_args()

    print(f"[env] cwd={os.getcwd()}", flush=True)
    print(f"[env] runner_python={sys.executable}", flush=True)
    print(f"[env] child_python={args.python}", flush=True)
    print(f"[env] platform={platform.platform()}", flush=True)

    if not args.skip_ldd:
        maybe_print_ldd(args.python)

    selected = args.scenario or list(SCENARIOS.keys())
    failed = 0
    for name in selected:
        rc = run_scenario(name, args.python)
        if rc != 0:
            failed += 1
    print(f"\n[summary] scenarios={len(selected)} failed={failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
