#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def _run(cmd: list[str]) -> int:
    print("+", " ".join(shlex.quote(x) for x in cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    print(f"  -> exit={proc.returncode}", flush=True)
    return int(proc.returncode)


def _as_bool_env(name: str, default: str = "0") -> bool:
    v = os.environ.get(name, default).strip().lower()
    return v in {"1", "true", "yes", "on"}


def main() -> int:
    profile = os.environ.get("HERMAX_CIBW_TEST_PROFILE", "full").strip().lower()
    allow_fail = _as_bool_env("HERMAX_CIBW_ALLOW_TEST_FAILURE", "0")
    timeout_s = int(os.environ.get("HERMAX_CIBW_COMPLIANCE_TIMEOUT", "180"))

    if profile not in {"smoke", "compliance", "full"}:
        print(
            f"Unknown HERMAX_CIBW_TEST_PROFILE={profile!r}; expected one of: smoke, compliance, full",
            file=sys.stderr,
        )
        return 2

    commands: list[list[str]] = []
    if profile == "smoke":
        commands.append(
            [
                sys.executable,
                str(TESTS / "run_compliance_matrix.py"),
                "--timeout",
                str(timeout_s),
                "--ci-policy",
                "none",
            ]
        )
    elif profile == "compliance":
        commands.append(
            [
                sys.executable,
                str(TESTS / "run_compliance_matrix.py"),
                "--timeout",
                str(timeout_s),
                "--ci-policy",
                "pass-skip",
            ]
        )
    else:
        # full
        commands.append(
            [
                sys.executable,
                str(TESTS / "run_compliance_matrix.py"),
                "--timeout",
                str(timeout_s),
                "--ci-policy",
                "pass-skip",
            ]
        )
        commands.append(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/model",
                "tests/core/test_portfolio.py",
                "tests/core/test_spb_maxsat_c_fps.py",
                "tests/core/test_nuwls_c_ibr.py",
                "tests/test_itotalizer_parity.py",
            ]
        )

    failures = 0
    for cmd in commands:
        rc = _run(cmd)
        if rc != 0:
            failures += 1

    if failures == 0:
        print("cibw tests: PASS", flush=True)
        return 0

    print(f"cibw tests: FAIL ({failures} command(s) failed)", flush=True)
    if allow_fail:
        print("HERMAX_CIBW_ALLOW_TEST_FAILURE=1 -> forcing success exit code", flush=True)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
