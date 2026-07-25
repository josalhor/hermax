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
DEFAULT_CPLEX_STUDIO = "/opt/ibm/ILOG/CPLEX_Studio2212"


def _run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), env=env)
    return int(proc.returncode)


def _require_cplex_env(env: dict[str, str]) -> tuple[str, str, str]:
    cplex_studio = (env.get("CPLEX_STUDIO") or DEFAULT_CPLEX_STUDIO).strip()
    cplex_inc_dir = (env.get("CPLEX_INC_DIR") or f"{cplex_studio}/cplex/include").strip()
    cplex_lib_dir = (env.get("CPLEX_LIB_DIR") or f"{cplex_studio}/cplex/lib/x86-64_linux/static_pic").strip()

    cplex_h = Path(cplex_inc_dir) / "ilcplex" / "cplex.h"
    if not cplex_h.is_file():
        raise FileNotFoundError(f"Missing CPLEX header: {cplex_h}")

    lib_dir = Path(cplex_lib_dir)
    libs = list(lib_dir.glob("libcplex*")) if lib_dir.is_dir() else []
    if not libs:
        raise FileNotFoundError(f"Missing CPLEX library under: {cplex_lib_dir}")

    return cplex_studio, cplex_inc_dir, cplex_lib_dir


def _cibw_cplex_env(
    *,
    current_python_only: bool,
    extra: list[str],
) -> tuple[dict[str, str], list[str]]:
    env = os.environ.copy()
    cplex_studio, cplex_inc_dir, cplex_lib_dir = _require_cplex_env(env)

    env["CIBW_CONTAINER_ENGINE"] = f"podman; create_args: --volume {cplex_studio}:{cplex_studio}:ro"
    env["CIBW_ENVIRONMENT_LINUX"] = (
        f"CPLEX_INC_DIR={cplex_inc_dir} "
        f"CPLEX_LIB_DIR={cplex_lib_dir} "
        "HERMAX_ENABLE_MAXHS=on "
        "HERMAX_ENABLE_IMAXHS=on "
        "SKIP_MAXHS=0 "
        "SKIP_IMAXHS=0 "
        f"HERMAX_CIBW_TEST_PROFILE={env.get('HERMAX_CIBW_TEST_PROFILE', 'full')} "
        f"HERMAX_CIBW_ALLOW_TEST_FAILURE={env.get('HERMAX_CIBW_ALLOW_TEST_FAILURE', '1')} "
        f"HERMAX_CIBW_COMPLIANCE_TIMEOUT={env.get('HERMAX_CIBW_COMPLIANCE_TIMEOUT', '180')}"
    )
    if current_python_only:
        py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}-manylinux_x86_64"
        env["CIBW_BUILD"] = py_tag

    cmd = [
        sys.executable,
        "-m",
        "cibuildwheel",
        "--output-dir",
        str(WHEELHOUSE),
    ]
    cmd.extend(extra)
    return env, cmd


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
    # cibuildwheel containers do not automatically inherit arbitrary host
    # environment variables. Forward the narrow solver selection explicitly.
    solver_include = env.get("HERMAX_SOLVER_INCLUDE", "").strip()
    if solver_include:
        existing = env.get("CIBW_ENVIRONMENT_LINUX", "").strip()
        forwarded = f"HERMAX_SOLVER_INCLUDE={solver_include}"
        env["CIBW_ENVIRONMENT_LINUX"] = f"{existing} {forwarded}".strip()
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


def cmd_cibw_full_cplex(args: argparse.Namespace) -> int:
    WHEELHOUSE.mkdir(exist_ok=True)
    env, cmd = _cibw_cplex_env(current_python_only=False, extra=args.extra)
    return _run(cmd, env=env)


def cmd_cibw_full_cplex_current(args: argparse.Namespace) -> int:
    WHEELHOUSE.mkdir(exist_ok=True)
    env, cmd = _cibw_cplex_env(current_python_only=True, extra=args.extra)
    return _run(cmd, env=env)


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

    cplex_full_p = sub.add_parser(
        "cibw-full-cplex",
        aliases=["cibw_full_cplex"],
        help="Build cibuildwheel matrix with CPLEX+MaxHS/iMaxHS enabled.",
    )
    cplex_full_p.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args passed to python -m cibuildwheel.")
    cplex_full_p.set_defaults(func=cmd_cibw_full_cplex)

    cplex_curr_p = sub.add_parser(
        "cibw-full-cplex-current",
        aliases=["cibw_full_cplex_current", "cibw-full-cplex-currentpython"],
        help="Build CPLEX-enabled wheel for current Python only (cpXY-manylinux_x86_64).",
    )
    cplex_curr_p.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args passed to python -m cibuildwheel.")
    cplex_curr_p.set_defaults(func=cmd_cibw_full_cplex_current)

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
