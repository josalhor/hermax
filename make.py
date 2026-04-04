#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WHEELHOUSE = ROOT / "wheelhouse"


def _run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), env=env)
    return int(proc.returncode)


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"removed {path.relative_to(ROOT)}")


def _iter_build_artifacts() -> list[Path]:
    targets: list[Path] = [
        ROOT / "build",
        ROOT / "dist",
        ROOT / "wheelhouse",
        ROOT / "hermax.egg-info",
        ROOT / ".pytest_cache",
        ROOT / "__pycache__",
    ]

    for pattern in ("*.so", "*.pyd", "*.dylib"):
        targets.extend(ROOT.glob(pattern))
        targets.extend((ROOT / "hermax").rglob(pattern))

    targets.extend(ROOT.rglob("__pycache__"))

    seen: set[Path] = set()
    unique_targets: list[Path] = []
    for path in targets:
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            continue
        if ".git" in rel.parts or "venv" in rel.parts or ".venv" in rel.parts:
            continue
        if path in seen:
            continue
        seen.add(path)
        unique_targets.append(path)
    return unique_targets


def cmd_clean(_args: argparse.Namespace) -> int:
    for path in _iter_build_artifacts():
        _remove_path(path)
    return 0


def cmd_current_wheel(args: argparse.Namespace) -> int:
    WHEELHOUSE.mkdir(exist_ok=True)
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}-*"
    env = os.environ.copy()
    env["CIBW_BUILD"] = py_tag
    cmd = [
        sys.executable,
        "-m",
        "cibuildwheel",
        "--output-dir",
        str(WHEELHOUSE),
    ]
    cmd.extend(args.extra)
    return _run(cmd, env=env)


def cmd_wheels(args: argparse.Namespace) -> int:
    WHEELHOUSE.mkdir(exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "cibuildwheel",
        "--output-dir",
        str(WHEELHOUSE),
    ]
    cmd.extend(args.extra)
    return _run(cmd)


def cmd_tests(args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        "tests/run_compliance_matrix.py",
        "--timeout",
        str(args.timeout),
    ]
    cmd.extend(args.extra)
    return _run(cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cross-platform Hermax task runner.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    clean_p = sub.add_parser("clean", help="Remove local build/test artifacts.")
    clean_p.set_defaults(func=cmd_clean)

    current_p = sub.add_parser(
        "current-wheel",
        aliases=["current_wheel"],
        help="Build a wheel for the current Python interpreter.",
    )
    current_p.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args passed to python -m build.")
    current_p.set_defaults(func=cmd_current_wheel)

    wheels_p = sub.add_parser(
        "wheels",
        help="Build all configured wheels via cibuildwheel.",
    )
    wheels_p.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args passed to python -m cibuildwheel.")
    wheels_p.set_defaults(func=cmd_wheels)

    tests_p = sub.add_parser(
        "tests",
        help="Run the primary local compliance test entrypoint.",
    )
    tests_p.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Per-solver timeout passed to tests/run_compliance_matrix.py.",
    )
    tests_p.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args passed to the test runner.")
    tests_p.set_defaults(func=cmd_tests)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
