"""Unified test entrypoint for Hermax.

Collects centralized ``test_*.py`` files from ``tests/``.

and runs them in one pytest invocation.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def collect_test_files() -> list[Path]:
    tests_root = ROOT / "tests"
    if not tests_root.exists():
        return []

    files = sorted(tests_root.rglob("test_*.py"))

    excluded = {}
    files = [f for f in files if f.name not in excluded]

    # de-duplicate while preserving order
    seen = set()
    unique: list[Path] = []
    for f in files:
        p = f.resolve()
        if p in seen:
            continue
        seen.add(p)
        unique.append(p)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all collected Hermax tests")
    args, passthrough = parser.parse_known_args()

    files = collect_test_files()
    if not files:
        print("No test files were found.")
        return 1

    print("Collected test files:")
    for f in files:
        print(f"- {f.relative_to(ROOT)}")

    has_pytest = importlib.util.find_spec("pytest") is not None
    run_cwd = ROOT / "tests"
    if has_pytest:
        cmd = [sys.executable, "-m", "pytest", *[str(f) for f in files], *passthrough]
        print("\nRunning:", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=run_cwd)
        return proc.returncode

    print("\npytest not available; falling back to direct script execution.")
    failures = 0
    for f in files:
        rel = f.relative_to(ROOT)
        cmd = [sys.executable, str(f)]
        print(f"\n>>> {rel}")
        proc = subprocess.run(cmd, cwd=run_cwd)
        if proc.returncode != 0:
            failures += 1
            print(f"FAILED: {rel} (exit {proc.returncode})")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
