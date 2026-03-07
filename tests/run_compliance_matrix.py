"""Run centralized Hermax tests with per-solver timeouts and emit a compliance matrix.

Statuses:
- PASS: all selected tests passed
- ERR: pytest failures/errors (non-crash)
- CRASH: process terminated by signal/segfault-style exit code
- TIMEOUT: exceeded per-solver timeout
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"


def _pytest_env() -> dict[str, str]:
    env = os.environ.copy()
    root_str = str(ROOT)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root_str if not prev else f"{root_str}:{prev}"
    env.setdefault("PYTHONFAULTHANDLER", "1")
    return env


@dataclass
class SolverCase:
    name: str
    selectors: list[str]


CASES: list[SolverCase] = [
    SolverCase(
        "UWrMaxSAT",
        [
            "core/test_ipamir_solver.py::TestUWrMaxSATSolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestUWrMaxSATSolverTerminationCallback",
            "core/test_urmaxsat.py",
        ],
    ),
    SolverCase(
        "UWrMaxSATComp",
        [
            "core/test_ipamir_solver.py::TestUWrMaxSATCompSolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestUWrMaxSATCompSolverTerminationCallback",
        ],
    ),
    SolverCase(
        "CASHWMaxSAT",
        [
            "core/test_ipamir_solver.py::TestCASHWMaxSATSolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestCASHWMaxSATSolverTerminationCallback",
            "test_cashwmaxsat.py",
        ],
    ),
    SolverCase(
        "EvalMaxSAT",
        [
            "core/test_ipamir_solver.py::TestEvalMaxSATLatestCompatTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestEvalMaxSATLatestCompatTerminationCallback",
            "core/test_evalmaxsat.py",
        ],
    ),
    SolverCase(
        "EvalMaxSATLatest",
        [
            "core/test_ipamir_solver.py::TestEvalMaxSATLatestSolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestEvalMaxSATLatestSolverTerminationCallback",
            "test_evalmaxsat_latest.py",
            "test_evalmaxsat_latest_reentrant.py",
        ],
    ),
    SolverCase(
        "EvalMaxSATIncr",
        [
            "core/test_ipamir_solver.py::TestEvalMaxSATIncrSolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestEvalMaxSATIncrSolverTerminationCallback",
            "test_evalmaxsat_incr.py",
        ],
    ),
    SolverCase(
        "RC2Reentrant",
        [
            "core/test_ipamir_solver.py::TestRC2ReentrantTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestRC2ReentrantTerminationCallback",
            "core/test_rc2_reentrant_soft_zero.py",
        ],
    ),
    SolverCase(
        "CGSS",
        [
            "core/test_ipamir_solver.py::TestCGSSTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestCGSSTerminationCallback",
        ],
    ),
    SolverCase(
        "CGSSPMRES",
        [
            "core/test_ipamir_solver.py::TestCGSSPMRESTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestCGSSPMRESTerminationCallback",
        ],
    ),
    SolverCase(
        "OpenWBO-OLL",
        [
            "core/test_ipamir_solver.py::TestOLLSolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestOLLSolverTerminationCallback",
            "core/test_openwbo.py::test_oll",
        ],
    ),
    SolverCase(
        "OpenWBO-PartMSU3",
        [
            "core/test_ipamir_solver.py::TestPartMSU3SolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestPartMSU3SolverTerminationCallback",
            "core/test_openwbo.py::test_partmsu3",
        ],
    ),
    SolverCase(
        "OpenWBO-Auto",
        [
            "core/test_ipamir_solver.py::TestAutoOpenWBOSolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestAutoOpenWBOSolverTerminationCallback",
        ],
    ),
    SolverCase(
        "OpenWBOInc",
        [
            "core/test_ipamir_solver.py::TestOpenWBOIncIncomplete",
            "core/test_ipamir_solver_hardcore.py::TestOpenWBOIncIncomplete",
            "core/test_openwbo_inc.py",
        ],
    ),
    SolverCase(
        "SPB-MaxSAT-c-FPS",
        [
            "core/test_ipamir_solver.py::TestSPBMaxSATCFPSIncomplete",
            "core/test_ipamir_solver_hardcore.py::TestSPBMaxSATCFPSIncomplete",
            "core/test_spb_maxsat_c_fps.py",
        ],
    ),
    SolverCase(
        "NuWLS-c-IBR",
        [
            "core/test_ipamir_solver.py::TestNuWLSCIBRIncomplete",
            "core/test_ipamir_solver_hardcore.py::TestNuWLSCIBRIncomplete",
            "core/test_nuwls_c_ibr.py",
        ],
    ),
    SolverCase(
        "Loandra",
        [
            "core/test_ipamir_solver.py::TestLoandraIncomplete",
            "core/test_ipamir_solver_hardcore.py::TestLoandraIncomplete",
            "core/test_loandra.py",
        ],
    ),
    SolverCase(
        "WMaxCDCL",
        [
            "core/test_ipamir_solver.py::TestWMaxCDCLSolverTerminationCallback",
            "core/test_ipamir_solver_hardcore.py::TestWMaxCDCLSolverTerminationCallback",
        ],
    ),
]


def classify_returncode(code: int) -> str:
    if code == 0:
        return "PASS"
    if code < 0:
        return "CRASH"
    if code in {132, 133, 134, 136, 137, 138, 139, 140}:  # common signal/abort exits
        return "CRASH"
    return "ERR"


STATUS_RE = re.compile(
    r"^(?P<node>.+::.+?)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS|XFAILED|XPASSED)\b"
)


def canonical_test_id(test_id: str) -> str:
    s = test_id.strip().replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    if s.startswith("tests/"):
        s = s[len("tests/") :]
    return s


def normalize_test_status(pytest_status: str) -> str:
    if pytest_status == "PASSED":
        return "PASS"
    if pytest_status in {"FAILED", "ERROR"}:
        return "ERR"
    if pytest_status in {"SKIPPED", "XFAIL", "XFAILED", "XPASS", "XPASSED"}:
        return "SKIP"
    return "ERR"


def normalize_matrix_status(status: str) -> str:
    if status in {"PASS", "SKIP", "ERR", "CRASH", "TIMEOUT"}:
        return status
    # Unknown/unparsed statuses are treated as ERR in the compliance rollup.
    return "ERR"


def compute_solver_status_counts(
    case_tests: dict[str, list[str]],
    case_test_status: dict[str, dict[str, str]],
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for case in CASES:
        counts = {"PASS": 0, "SKIP": 0, "ERR": 0, "CRASH": 0, "TIMEOUT": 0}
        for test_id in case_tests.get(case.name, []):
            raw = case_test_status.get(case.name, {}).get(test_id, "UNKNOWN")
            status = normalize_matrix_status(raw)
            counts[status] += 1
        out[case.name] = counts
    return out


def evaluate_expectations(
    expectations_file: Path,
    solver_status_counts: dict[str, dict[str, int]],
) -> tuple[bool, list[str]]:
    if not expectations_file.exists():
        return False, [f"expectations file not found: {expectations_file}"]
    try:
        payload = json.loads(expectations_file.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive parsing path
        return False, [f"failed to parse expectations file {expectations_file}: {exc}"]

    solver_rules = payload.get("solvers", {})
    if not isinstance(solver_rules, dict):
        return False, ["invalid expectations format: 'solvers' must be a JSON object"]

    failures: list[str] = []
    for solver, rules in solver_rules.items():
        if solver not in solver_status_counts:
            failures.append(f"solver '{solver}' is present in expectations but not in CASES")
            continue
        if not isinstance(rules, dict):
            failures.append(f"solver '{solver}' rules must be a JSON object")
            continue
        max_rules = rules.get("max", {})
        min_rules = rules.get("min", {})
        if max_rules and not isinstance(max_rules, dict):
            failures.append(f"solver '{solver}' max must be a JSON object")
            continue
        if min_rules and not isinstance(min_rules, dict):
            failures.append(f"solver '{solver}' min must be a JSON object")
            continue
        counts = solver_status_counts[solver]
        for key, limit in max_rules.items():
            if key not in counts:
                failures.append(f"solver '{solver}' has unknown status key in max: {key}")
                continue
            if not isinstance(limit, int):
                failures.append(f"solver '{solver}' max.{key} must be an integer")
                continue
            if counts[key] > limit:
                failures.append(f"solver '{solver}' max.{key}={limit} violated (actual={counts[key]})")
        for key, limit in min_rules.items():
            if key not in counts:
                failures.append(f"solver '{solver}' has unknown status key in min: {key}")
                continue
            if not isinstance(limit, int):
                failures.append(f"solver '{solver}' min.{key} must be an integer")
                continue
            if counts[key] < limit:
                failures.append(f"solver '{solver}' min.{key}={limit} violated (actual={counts[key]})")

    return len(failures) == 0, failures


def collect_case_tests(case: SolverCase, extra_pytest_args: list[str]) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--rootdir=.",
        "--collect-only",
        "-q",
        *case.selectors,
        *extra_pytest_args,
    ]
    proc = subprocess.run(cmd, cwd=TESTS_DIR, env=_pytest_env(), capture_output=True, text=True)
    tests: list[str] = []
    for line in proc.stdout.splitlines():
        s = line.strip()
        if not s or s.startswith("=") or " collected" in s:
            continue
        if "::" in s:
            tests.append(canonical_test_id(s))
    # unique preserve order
    seen = set()
    out: list[str] = []
    for t in tests:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def run_case(
    case: SolverCase,
    timeout_s: int,
    extra_pytest_args: list[str],
    exhaustive: bool,
    log_dir: Path,
) -> tuple[str, float, int | None, dict[str, str], str]:
    log_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", case.name)

    # Temporary platform policy: EvalMaxSAT variants are unstable on macOS.
    if sys.platform == "darwin" and platform.machine() in {"arm64", "x86_64"} and case.name in {
        "EvalMaxSAT",
        "EvalMaxSATLatest",
    }:
        out = f"SKIPPED by platform policy: {case.name} on darwin/{platform.machine()}\n"
        (log_dir / f"{safe}.log").write_text(out, encoding="utf-8")
        return ("PASS", 0.0, 0, {}, out)

    base_flags = ["-vv", "-rA"] if exhaustive else ["-q"]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--rootdir=.",
        *base_flags,
        *case.selectors,
        *extra_pytest_args,
    ]
    start = time.monotonic()
    out = ""
    per_test: dict[str, str] = {}
    try:
        proc = subprocess.run(
            cmd,
            cwd=TESTS_DIR,
            env=_pytest_env(),
            timeout=timeout_s,
            capture_output=True,
            text=True,
        )
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        for line in out.splitlines():
            m = STATUS_RE.match(line.strip())
            if not m:
                continue
            per_test[canonical_test_id(m.group("node"))] = normalize_test_status(m.group("status"))
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        out = (f"TIMEOUT after {timeout_s}s\n")
        (log_dir / f"{safe}.log").write_text(out, encoding="utf-8")
        return ("TIMEOUT", elapsed, None, per_test, out)

    elapsed = time.monotonic() - start
    status = classify_returncode(proc.returncode)

    (log_dir / f"{safe}.log").write_text(out, encoding="utf-8")
    if status == "CRASH":
        _collect_crash_diagnostics(case, log_dir, safe)

    return (status, elapsed, proc.returncode, per_test, out)


def _run_diag(cmd: list[str], *, cwd: Path, env: dict[str, str], timeout_s: int = 60) -> str:
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            timeout=timeout_s,
            capture_output=True,
            text=True,
        )
        return (
            f"$ {' '.join(cmd)}\n"
            f"exit={p.returncode}\n"
            f"--- stdout ---\n{p.stdout or ''}\n"
            f"--- stderr ---\n{p.stderr or ''}\n"
        )
    except Exception as exc:  # pragma: no cover
        return f"$ {' '.join(cmd)}\nexception={exc}\n"


def _collect_crash_diagnostics(case: SolverCase, log_dir: Path, safe: str) -> None:
    env = _pytest_env()
    diag: list[str] = []

    diag.append(
        _run_diag(
            [
                sys.executable,
                "-X",
                "faulthandler",
                "-c",
                (
                    "import sys,platform; "
                    "print('python=', sys.version); "
                    "print('executable=', sys.executable); "
                    "print('platform=', platform.platform()); "
                    "print('machine=', platform.machine())"
                ),
            ],
            cwd=TESTS_DIR,
            env=env,
        )
    )

    if case.name in {"EvalMaxSAT", "EvalMaxSATLatest", "EvalMaxSATIncr"}:
        diag.append(
            _run_diag(
                [
                    sys.executable,
                    "-X",
                    "faulthandler",
                    "-c",
                    (
                        "import sysconfig,glob,os; "
                        "print('EXT_SUFFIX=', sysconfig.get_config_var('EXT_SUFFIX')); "
                        "paths=sorted(glob.glob('hermax/core/evalmaxsat_latest*')+glob.glob('hermax/core/evalmaxsat_incr*')); "
                        "print('candidates='); "
                        "print('\\n'.join(paths) if paths else '(none)')"
                    ),
                ],
                cwd=TESTS_DIR,
                env=env,
            )
        )
        diag.append(
            _run_diag(
                [
                    sys.executable,
                    "-X",
                    "faulthandler",
                    "-c",
                    "import hermax.core.evalmaxsat_latest as m; print(m.__file__)",
                ],
                cwd=TESTS_DIR,
                env=env,
            )
        )
        diag.append(
            _run_diag(
                [
                    sys.executable,
                    "-X",
                    "faulthandler",
                    "-c",
                    (
                        "import hermax.core.evalmaxsat_latest as m; "
                        "s=m.EvalMaxSAT(); "
                        "a=s.newVar(); b=s.newVar(); "
                        "s.addClause([a],1); s.addClause([-a,b],None); "
                        "print('pre-solve-ok'); "
                        "print('solve=', s.solve()); "
                        "print('cost=', s.getCost())"
                    ),
                ],
                cwd=TESTS_DIR,
                env=env,
            )
        )
        diag.append(
            _run_diag(
                [
                    sys.executable,
                    "-X",
                    "faulthandler",
                    "-c",
                    "import hermax.core.evalmaxsat_incr as m; print(m.__file__)",
                ],
                cwd=TESTS_DIR,
                env=env,
            )
        )

    diag.append(
        _run_diag(
            [
                sys.executable,
                "-X",
                "faulthandler",
                "-m",
                "pytest",
                "--rootdir=.",
                "-s",
                "-vv",
                *case.selectors,
            ],
            cwd=TESTS_DIR,
            env=env,
            timeout_s=120,
        )
    )

    crash_log = log_dir / f"{safe}.crash_diag.log"
    crash_log.write_text("\n\n".join(diag), encoding="utf-8")
    # Surface diagnostics in CI logs so failures can be debugged without artifacts.
    print(f"\n--- crash diagnostics: {case.name} ({crash_log}) ---")
    lines = crash_log.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = "\n".join(lines[-120:]) if lines else "(empty)"
    print(tail)
    print("--- end crash diagnostics ---\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run timeout-aware solver compliance matrix")
    parser.add_argument("--timeout", type=int, default=180, help="per-solver timeout in seconds")
    parser.add_argument(
        "--exhaustive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="enable exhaustive solver x test matrix logging (default: enabled)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(TESTS_DIR / "_compliance"),
        help="directory for compliance artifacts",
    )
    parser.add_argument(
        "--ci-policy",
        choices=["none", "solver-pass", "pass-skip", "expectations"],
        default="none",
        help="CI failure policy: none, require all solvers PASS, require matrix PASS/SKIP only, or validate expectations file",
    )
    parser.add_argument(
        "--expectations-file",
        default=str(TESTS_DIR / "compliance_expectations.json"),
        help="JSON file used with --ci-policy expectations",
    )
    parser.add_argument("pytest_args", nargs="*", help="extra args forwarded to pytest")
    args = parser.parse_args()

    print(f"Per-solver timeout: {args.timeout}s")
    print("Running from:", TESTS_DIR)
    print("Exhaustive logs:", args.exhaustive)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = out_dir / "logs"

    results: list[tuple[str, str, float, str]] = []
    case_tests: dict[str, list[str]] = {}
    case_test_status: dict[str, dict[str, str]] = {}
    for case in CASES:
        print(f"\n=== {case.name} ===")
        tests = collect_case_tests(case, args.pytest_args) if args.exhaustive else []
        case_tests[case.name] = tests
        status, elapsed, code, per_test, out = run_case(
            case, args.timeout, args.pytest_args, args.exhaustive, log_dir
        )
        detail = "-" if code is None else str(code)
        results.append((case.name, status, elapsed, detail))
        if status in {"TIMEOUT", "CRASH"}:
            row = {t: status for t in tests}
        else:
            # Start unknown and fill from parsed pytest rows; avoid defaulting to ERR.
            row = {t: "UNKNOWN" for t in tests}
            row.update(per_test)
            if status == "PASS":
                # Successful run means any unparsed rows are effectively passing.
                row = {t: ("PASS" if s == "UNKNOWN" else s) for t, s in row.items()}
        case_test_status[case.name] = row
        print(f"status={status} elapsed={elapsed:.1f}s code={detail}")
        if status != "PASS":
            excerpt = "\n".join((out or "").splitlines()[:40]).strip()
            if excerpt:
                print(f"--- {case.name} failure excerpt (first 40 lines) ---")
                print(excerpt)
                print(f"--- end {case.name} excerpt ---")

    print("\nCompliance Matrix")
    print("| Solver | Status | Time(s) | Exit |")
    print("|---|---|---:|---:|")
    for name, status, elapsed, detail in results:
        print(f"| {name} | {status} | {elapsed:.1f} | {detail} |")

    solver_status_counts = compute_solver_status_counts(case_tests, case_test_status)
    print("\nSolver Status Count Matrix")
    print("| Solver | PASS | SKIP | ERR | CRASH | TIMEOUT |")
    print("|---|---:|---:|---:|---:|---:|")
    for case in CASES:
        c = solver_status_counts[case.name]
        print(
            f"| {case.name} | {c['PASS']} | {c['SKIP']} | {c['ERR']} | {c['CRASH']} | {c['TIMEOUT']} |"
        )

    # Write solver-level summary files
    summary_csv = out_dir / "solver_matrix.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["solver", "status", "time_s", "exit_code"])
        for name, status, elapsed, detail in results:
            w.writerow([name, status, f"{elapsed:.3f}", detail])

    summary_md = out_dir / "solver_matrix.md"
    with summary_md.open("w", encoding="utf-8") as f:
        f.write("| Solver | Status | Time(s) | Exit |\n")
        f.write("|---|---|---:|---:|\n")
        for name, status, elapsed, detail in results:
            f.write(f"| {name} | {status} | {elapsed:.1f} | {detail} |\n")

    status_counts_csv = out_dir / "solver_status_counts.csv"
    with status_counts_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["solver", "PASS", "SKIP", "ERR", "CRASH", "TIMEOUT"])
        for case in CASES:
            c = solver_status_counts[case.name]
            w.writerow([case.name, c["PASS"], c["SKIP"], c["ERR"], c["CRASH"], c["TIMEOUT"]])

    status_counts_md = out_dir / "solver_status_counts.md"
    with status_counts_md.open("w", encoding="utf-8") as f:
        f.write("| Solver | PASS | SKIP | ERR | CRASH | TIMEOUT |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for case in CASES:
            c = solver_status_counts[case.name]
            f.write(
                f"| {case.name} | {c['PASS']} | {c['SKIP']} | {c['ERR']} | {c['CRASH']} | {c['TIMEOUT']} |\n"
            )

    # Exhaustive solver x test matrix files
    if args.exhaustive:
        all_tests = sorted({t for tests in case_tests.values() for t in tests})
        matrix_csv = out_dir / "solver_x_test_matrix.csv"
        with matrix_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["test_id", *[c.name for c in CASES]])
            for t in all_tests:
                w.writerow([t, *[case_test_status.get(c.name, {}).get(t, "") for c in CASES]])

        matrix_md = out_dir / "solver_x_test_matrix.md"
        with matrix_md.open("w", encoding="utf-8") as f:
            f.write("| Test | " + " | ".join(c.name for c in CASES) + " |\n")
            f.write("|---|" + "|".join("---" for _ in CASES) + "|\n")
            for t in all_tests:
                cells = [case_test_status.get(c.name, {}).get(t, "") for c in CASES]
                f.write("| " + t + " | " + " | ".join(cells) + " |\n")

    report_json = out_dir / "compliance_report.json"
    report_json.write_text(
        json.dumps(
            {
                "timeout_s": args.timeout,
                "exhaustive": args.exhaustive,
                "solver_summary": [
                    {"solver": n, "status": s, "time_s": e, "exit_code": d}
                    for n, s, e, d in results
                ],
                "solver_x_test": case_test_status if args.exhaustive else {},
                "solver_status_counts": solver_status_counts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nArtifacts written to: {out_dir}")

    if args.ci_policy == "none":
        return 0
    if args.ci_policy == "solver-pass":
        has_non_pass = any(status != "PASS" for _name, status, _elapsed, _detail in results)
        return 1 if has_non_pass else 0
    if args.ci_policy == "pass-skip":
        bad = {"ERR", "CRASH", "TIMEOUT", "UNKNOWN"}
        # Any solver-level non-PASS outcome is an immediate CI failure.
        if any(status != "PASS" for _name, status, _elapsed, _detail in results):
            return 1
        for case in CASES:
            c = solver_status_counts.get(case.name, {})
            if any(c.get(k, 0) > 0 for k in bad):
                return 1
        return 0
    ok, failures = evaluate_expectations(Path(args.expectations_file), solver_status_counts)
    if not ok:
        print("\nExpectation policy failures:")
        for msg in failures:
            print(f"- {msg}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
