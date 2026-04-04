# Tests

This directory is the centralized test entrypoint for Hermax.

## Layout

- `tests/core/`: migrated solver/core tests (including data fixtures under `tests/core/data/` and related helper dirs).
- `tests/test_*.py`: top-level package tests migrated from repo root.
- `tests/run_collected_tests.py`: unified test collector/runner over centralized tests.
- `tests/run_compliance_matrix.py`: timeout-aware solver compliance runner that builds solver-level and solver x test matrices.
- `tests/fuzzing/`: grammar-aware WCNF fuzzing, comparison, and optional reduction.
- `tests/randomized/`: random testing over real `.wcnf` instances with assumptions/weight perturbations.
- `tests/compliance_expectations.example.json`: example expectations policy file for CI gating.

## Solver Scope

Current compliance matrix includes all active solvers except MaxHS/IMaxHS (intentionally excluded/commented out for now).

## Main Runner

Run with default exhaustive logging:

```bash
python tests/run_compliance_matrix.py --timeout 180
```

Useful flags:

- `--timeout <sec>`: per-solver timeout.
- `--exhaustive / --no-exhaustive`: exhaustive solver x test logging (default: enabled).
- `--out-dir <path>`: artifact output directory (default: `tests/_compliance`).
- `--ci-policy {none,solver-pass,pass-skip,expectations}`: CI exit policy.
- `--expectations-file <path>`: JSON file for expectations policy.
- additional pytest args can be appended at the end.

## Matrix Semantics

### 1) Solver-level matrix

`solver_matrix.csv/.md` contains one row per solver with overall run status:

- `PASS`: solver run completed with pytest exit code 0.
- `ERR`: solver run completed but had failures/errors.
- `CRASH`: process crashed/aborted (signal-like exits).
- `TIMEOUT`: exceeded per-solver timeout.

### 2) Solver x test matrix (exhaustive)

`solver_x_test_matrix.csv/.md` contains test-level status per solver:

- `PASS`, `SKIP`, `ERR`, `CRASH`, `TIMEOUT`.

### 3) Solver status count matrix

`solver_status_counts.csv/.md` aggregates counts per solver over:

- `PASS | SKIP | ERR | CRASH | TIMEOUT`

This is the high-level picture for regression tracking and CI policy.

## Artifacts

Default output directory: `tests/_compliance/`

- `solver_matrix.csv`
- `solver_matrix.md`
- `solver_x_test_matrix.csv` (when exhaustive)
- `solver_x_test_matrix.md` (when exhaustive)
- `solver_status_counts.csv`
- `solver_status_counts.md`
- `compliance_report.json`
- `logs/<solver>.log`

## CI Policy

The runner exit code is controlled by `--ci-policy`:

- `none`: always exit 0 (reporting mode).
- `solver-pass`: exit nonzero if any solver overall status is not `PASS`.
- `pass-skip`: strict mode; exit nonzero if any solver-level status is non-`PASS` or any solver x test cell is not `PASS`/`SKIP`.
- `expectations`: evaluate per-solver count constraints from a JSON file.

### Expectations policy format

Example:

```json
{
  "solvers": {
    "RC2Fork": {
      "max": {"ERR": 0, "CRASH": 0, "TIMEOUT": 0}
    },
    "OpenWBOInc": {
      "max": {"ERR": 0, "CRASH": 0, "TIMEOUT": 0}
    }
  }
}
```

Supported keys per solver rule:

- `max`: upper bounds on any of `PASS, SKIP, ERR, CRASH, TIMEOUT`
- `min`: lower bounds on any of `PASS, SKIP, ERR, CRASH, TIMEOUT`

A violation causes nonzero exit.

## Recommended CI rollout

1. Keep reporting mode in wheel builds first:
   - `--ci-policy none`
2. Define a `tests/compliance_expectations.json` for known-sound solvers.
3. Switch CI to:
   - `--ci-policy expectations --expectations-file tests/compliance_expectations.json`

This allows known-buggy solvers to be tracked without blocking releases, while enforcing strict quality on known-sound solvers.

## cibuildwheel integration

Current `pyproject.toml` test command runs:

```bash
python {project}/tests/run_compliance_matrix.py --timeout 180 --ci-policy pass-skip
```

## Random Testing

Run random testing over real benchmark instances:

```bash
python -m tests.randomized --data-dir tests/data --iterations 200
```

Indefinite run:

```bash
python -m tests.randomized --data-dir tests/data --forever --interactive
```

Artifacts are written to `tests/_random/` by default, including:

- per-case summary files under `tests/_random/summaries/`
- fault logs under `tests/_random/fault_logs/`
- anomaly diagnostics under `tests/_random/anomaly_logs/`
- live dashboard snapshot at `tests/_random/live_dashboard.txt`
