# MaxSAT Fuzzing + Delta Debugging

This folder contains a standalone grammar-aware WCNF fuzzer, cross-solver comparator, and greedy delta debugger inspired by Paxian & Biere (2023).

## Entrypoint

```bash
python -m tests.fuzzing --help
```

Equivalent module entrypoint:

```bash
python -m tests.fuzzing.run_fuzzing --help
```

Interactive dashboard mode:

```bash
python -m tests.fuzzing --interactive
```

## Interactive Dashboard

The dashboard is redrawn in-place and shows:

- Solver stability matrix (`solver x PASS|SKIP|ERR|CRASH|TIMEOUT`)
- Fault totals
- Top error-trigger feature tags
- Top skip reasons
- `iter_progress`, `solver_progress`, `phase`
- Last anomaly artifact path (`last_alert`)

`SKIP` means solver unavailable/unsupported in current runtime and is not counted as a fuzzing fault.

Default solver policy:

- `OpenWBOInc` is excluded by default.
- `OpenWBO-PartMSU3` is treated as `SKIP` on weighted instances in fuzzing mode.

## Important Semantics

- Duplicate unit soft clauses are coalesced by literal before injection into solvers.
  - This is required because IPAMIR-style soft-literal APIs are update/declaration based.
  - Without coalescing, repeated unit soft clauses can produce false consistency mismatches.

## All-Failed Anomaly Logs

If all considered solvers for a case end in `ERR|CRASH|TIMEOUT`, an anomaly file is written:

- `anomaly_logs/<case_id>__ALL_FAILED.json`

By default, `OpenWBO-PartMSU3` is ignored in this detector. Override with:

```bash
python -m tests.fuzzing --all-failed-ignore SolverA,SolverB
```

## Main Components

- `wcnfuzz.py`: layered WCNF generator (`WCNFuzz`)
- `regression.py`: static edge-case corpus
- `worker.py`: isolated subprocess runner (one solver, one case)
- `compare.py`: multi-solver comparator + fault classification
- `reducer.py`: greedy delta-debugger
- `run_fuzzing.py`: top-level orchestration

## Timeouts

- `--per-solver-timeout`: timeout per solver subprocess
- `--overall-timeout`: global wall-clock budget (`<= 0` disables)

## Overnight Run

```bash
venv/bin/python -m tests.fuzzing --forever --overall-timeout 0 --per-solver-timeout 20 --interactive --out-dir tests/_fuzzing_overnight
```

Optional stream capture:

```bash
venv/bin/python -m tests.fuzzing --forever --overall-timeout 0 --per-solver-timeout 20 --interactive --out-dir tests/_fuzzing_overnight | tee tests/_fuzzing_overnight/live.log
```

## Output Layout

- `config.json`
- `cases/*.case.json`, `cases/*.case.wcnf`
- `summaries/*.summary.json`
- `fault_logs/*.log`
- `anomaly_logs/*.json`
- `live_dashboard.txt`
- `final_summary.json`
