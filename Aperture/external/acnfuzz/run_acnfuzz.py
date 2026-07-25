import argparse
import csv
from datetime import datetime
import os
import shutil
import subprocess
import tempfile
import time


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACNF_FUZZER_PATH = os.path.join(SCRIPT_DIR, "generateACNF.sh")

SOLVERS = {
    "Aperture_Glucose": {"path": os.path.join(SCRIPT_DIR, "solvers", "aperture_Glucose"), "acnf_capable": True},
    "Aperture_IntelSAT": {"path": os.path.join(SCRIPT_DIR, "solvers", "aperture_IntelSAT"), "acnf_capable": True},
    "EvalMaxSAT": {"path": os.path.join(SCRIPT_DIR, "solvers", "EvalMaxSAT_bin"), "acnf_capable": False},
}

EXPECTED_SOLVER_RETURN_CODES = {0, 10, 20}


def log(message, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}][{level}] {message}", flush=True)


def run_process(command, timeout=None):
    kwargs = {}
    if timeout is not None:
        kwargs["timeout"] = timeout

    if os.name == "nt":
        kwargs["shell"] = False

    if hasattr(subprocess, "run"):
        if tuple(map(int, os.sys.version_info[:2])) >= (3, 7):
            kwargs["capture_output"] = True
            kwargs["text"] = True
        else:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE
            kwargs["universal_newlines"] = True
        return subprocess.run(command, **kwargs)

    raise RuntimeError("Unsupported Python runtime")


def parse_acnf_queries(acnf_path):
    queries = []
    with open(acnf_path, "r", encoding="utf-8") as f:
        current_clauses = []
        accumulated_clauses = []
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("s"):
                parsed_assumptions = list(map(int, stripped.split()[1:-1]))
                active_clauses = list(accumulated_clauses)
                active_clauses.extend(current_clauses)
                queries.append(
                    {
                        "type": "s",
                        "assumptions": parsed_assumptions,
                        "clauses": current_clauses,
                        "active_clauses": active_clauses,
                    }
                )
                accumulated_clauses = active_clauses
                current_clauses = []
            elif stripped.startswith("u"):
                parsed_line = stripped.split()
                num_assumptions = int(parsed_line[1])
                num_soft_lits = int(parsed_line[2])
                parsed_assumptions = list(map(int, parsed_line[3 : 3 + num_assumptions]))
                parsed_soft_lits = []
                for i in range(num_soft_lits):
                    soft_lit = int(parsed_line[3 + num_assumptions + i])
                    parsed_soft_lits.append((1, soft_lit))
                active_clauses = list(accumulated_clauses)
                active_clauses.extend(current_clauses)
                queries.append(
                    {
                        "type": "u",
                        "assumptions": parsed_assumptions,
                        "soft_lits": parsed_soft_lits,
                        "clauses": current_clauses,
                        "active_clauses": active_clauses,
                    }
                )
                accumulated_clauses = active_clauses
                current_clauses = []
            elif stripped.startswith("w"):
                parsed_line = stripped.split()
                num_assumptions = int(parsed_line[1])
                num_soft_lits = int(parsed_line[2])
                parsed_assumptions = list(map(int, parsed_line[3 : 3 + num_assumptions]))
                parsed_soft_lits = []
                weighted_start = 3 + num_assumptions
                for i in range(num_soft_lits):
                    weight = int(parsed_line[weighted_start + 2 * i])
                    soft_lit = int(parsed_line[weighted_start + 2 * i + 1])
                    parsed_soft_lits.append((weight, soft_lit))
                active_clauses = list(accumulated_clauses)
                active_clauses.extend(current_clauses)
                queries.append(
                    {
                        "type": "w",
                        "assumptions": parsed_assumptions,
                        "soft_lits": parsed_soft_lits,
                        "clauses": current_clauses,
                        "active_clauses": active_clauses,
                    }
                )
                accumulated_clauses = active_clauses
                current_clauses = []
            elif not stripped.startswith("c") and not stripped.startswith("p"):
                parsed_clause = list(map(int, stripped.split()[:-1]))
                current_clauses.append(parsed_clause)
    return queries


def generate_acnf(acnf_file, generated_acnf_path):
    if acnf_file is not None:
        src_abs = os.path.abspath(acnf_file)
        dst_abs = os.path.abspath(generated_acnf_path)
        if src_abs != dst_abs:
            with open(src_abs, "r", encoding="utf-8") as src, open(dst_abs, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        return parse_acnf_queries(generated_acnf_path)

    output = run_process([ACNF_FUZZER_PATH])
    with open(generated_acnf_path, "w", encoding="utf-8") as f:
        f.write(output.stdout)
    return parse_acnf_queries(generated_acnf_path)


def parse_acnf_output(output):
    lines = output.splitlines()
    results = []
    current_result = None

    for raw_line in lines:
        line = raw_line.strip()

        if line.startswith("s "):
            if current_result is not None:
                results.append(current_result)
                current_result = None

            status_text = line[2:].strip().upper()
            if status_text.startswith("SATISFIABLE") or status_text.startswith("OPTIMUM FOUND"):
                current_result = {"status": "SAT", "val": None, "model": None}
            elif status_text.startswith("UNSATISFIABLE"):
                results.append({"status": "UNSAT"})
            else:
                results.append({"status": "UNKNOWN"})
            continue

        if current_result is None:
            continue

        if line.startswith("o "):
            parts = line.split(maxsplit=1)
            if len(parts) > 1:
                try:
                    current_result["val"] = int(parts[1].split()[0])
                except ValueError:
                    current_result["val"] = None
        elif line.startswith("v "):
            model_chunk = "".join(line[2:].split())
            current_result["model"] = model_chunk or None
            results.append(current_result)
            current_result = None

    if current_result is not None:
        results.append(current_result)

    return results


def parse_wcnf_output(output):
    lines = output.splitlines()
    results = []
    for line in lines:
        line = line.strip()
        if line.startswith("s "):
            status_text = line[2:].strip().upper()
            if status_text.startswith("SATISFIABLE") or status_text.startswith("OPTIMUM FOUND"):
                results.append({"status": "SAT", "val": None, "model": None})
            elif status_text.startswith("UNSATISFIABLE"):
                results.append({"status": "UNSAT"})
            else:
                results.append({"status": "UNKNOWN"})
        elif line.startswith("o ") and results and results[-1]["status"] == "SAT":
            parts = line.split(maxsplit=1)
            if len(parts) > 1:
                try:
                    results[-1]["val"] = int(parts[1].split()[0])
                except ValueError:
                    results[-1]["val"] = None
        elif line.startswith("v ") and results and results[-1]["status"] == "SAT":
            model_chunk = "".join(line[2:].split())
            results[-1]["model"] = model_chunk or None
    return results


def literal_is_satisfied(literal, model):
    if model is None:
        return False, "model is missing"

    variable = abs(literal)
    if variable == 0:
        return False, "literal 0 is invalid"

    if variable - 1 >= len(model):
        return False, f"variable {variable} exceeds model length {len(model)}"

    model_value = model[variable - 1] == "1"
    return (model_value if literal > 0 else not model_value), None


def clause_is_satisfied(clause, model):
    for literal in clause:
        satisfied, error = literal_is_satisfied(literal, model)
        if error is not None:
            return False, error
        if satisfied:
            return True, None
    return False, None


def save_bugged_acnf_snapshot(source_path, target_dir, iteration, run_timestamp):
    if not os.path.exists(source_path):
        return None
    run_dir = os.path.join(target_dir, run_timestamp)
    os.makedirs(run_dir, exist_ok=True)
    filename = f"iteration-{iteration}.acnf"
    destination = os.path.join(run_dir, filename)
    shutil.copyfile(source_path, destination)
    return destination


def append_error_rows_to_csv(csv_path, error_rows):
    if not error_rows:
        return

    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    header = ["run_timestamp", "timestamp", "iteration", "solver", "query_index", "error_type", "message"]
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerows(error_rows)


def record_error(error_rows, iteration, solver, query_index, error_type, message, run_timestamp=None):
    log(f"it={iteration} solver={solver} q={query_index}: {message}", level="ERROR")
    error_rows.append(
        {
            "run_timestamp": run_timestamp or "",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "iteration": iteration,
            "solver": solver,
            "query_index": query_index,
            "error_type": error_type,
            "message": message,
        }
    )


def compare_solver_results_per_iteration(queries, solver_results, iteration, error_rows, run_timestamp):
    status_mismatches = 0
    value_mismatches = 0

    for query_idx, query in enumerate(queries):
        statuses_by_solver = {}
        values_by_solver = {}

        for solver_name, parsed_results in solver_results.items():
            if query_idx < len(parsed_results):
                item = parsed_results[query_idx]
                statuses_by_solver[solver_name] = item.get("status")
                values_by_solver[solver_name] = item.get("val")

        if len(statuses_by_solver) < 2:
            continue

        status_set = set(statuses_by_solver.values())
        if len(status_set) > 1:
            status_mismatches += 1
            status_str = ", ".join(f"{s}:{v}" for s, v in statuses_by_solver.items())
            record_error(
                error_rows,
                iteration,
                "ALL",
                query_idx,
                "cross_solver_status_mismatch",
                f"Status mismatch ({status_str}) for query type {query.get('type')}",
                run_timestamp,
            )

        sat_solvers = [s for s, st in statuses_by_solver.items() if st == "SAT"]
        if len(sat_solvers) > 1:
            sat_values = set(values_by_solver[s] for s in sat_solvers if values_by_solver[s] is not None)
            if len(sat_values) > 1:
                value_mismatches += 1
                value_str = ", ".join(f"{s}:{values_by_solver[s]}" for s in sat_solvers)
                record_error(
                    error_rows,
                    iteration,
                    "ALL",
                    query_idx,
                    "cross_solver_value_mismatch",
                    f"Value mismatch ({value_str}) for query type {query.get('type')}",
                    run_timestamp,
                )

    return status_mismatches, value_mismatches


def validate_model_and_costs(queries, solver_name, output, iteration, error_rows, run_timestamp):
    for i in range(min(len(output), len(queries))):
        query = queries[i]
        result = output[i]

        if result.get("status") != "SAT":
            continue

        model = result.get("model")

        for assumption in query.get("assumptions", []):
            lit = int(assumption)
            satisfied, error = literal_is_satisfied(lit, model)
            if error is not None:
                record_error(
                    error_rows,
                    iteration,
                    solver_name,
                    i,
                    "assumption_model_bounds",
                    f"Cannot evaluate assumption {lit}: {error}",
                    run_timestamp,
                )
            elif not satisfied:
                record_error(
                    error_rows,
                    iteration,
                    solver_name,
                    i,
                    "assumption_violation",
                    f"Assumption {lit} not satisfied by model",
                    run_timestamp,
                )

        active_clauses = query.get("active_clauses", query.get("clauses", []))
        for clause_index, clause in enumerate(active_clauses):
            sat, err = clause_is_satisfied(clause, model)
            if err is not None:
                record_error(
                    error_rows,
                    iteration,
                    solver_name,
                    i,
                    "clause_eval_error",
                    f"Clause {clause_index} evaluation failed: {err}; clause={clause}",
                    run_timestamp,
                )
            elif not sat:
                record_error(
                    error_rows,
                    iteration,
                    solver_name,
                    i,
                    "clause_violation",
                    f"Clause {clause_index} violated; clause={clause}",
                    run_timestamp,
                )

        if query.get("type") in {"u", "w"}:
            sat_weight = 0
            for weight, soft_lit in query.get("soft_lits", []):
                satisfied, error = literal_is_satisfied(int(soft_lit), model)
                if error is not None:
                    record_error(
                        error_rows,
                        iteration,
                        solver_name,
                        i,
                        "soft_lit_model_bounds",
                        f"Cannot evaluate soft literal {soft_lit}: {error}",
                        run_timestamp,
                    )
                elif satisfied:
                    sat_weight += weight

            solver_val = result.get("val")
            if solver_val is not None and sat_weight != solver_val:
                record_error(
                    error_rows,
                    iteration,
                    solver_name,
                    i,
                    "cost_mismatch",
                    f"Expected satisfied weight {solver_val}, computed {sat_weight}",
                    run_timestamp,
                )


def run_solver_for_queries(solver_name, solver_info, local_acnf_path, local_wcnf_path, queries, solver_timeout, iteration, error_rows, run_timestamp):
    if solver_info["acnf_capable"]:
        result = run_process([solver_info["path"], local_acnf_path, "-m", "acnf"], timeout=solver_timeout)
        if result.returncode not in EXPECTED_SOLVER_RETURN_CODES:
            record_error(
                error_rows,
                iteration,
                solver_name,
                -1,
                "solver_non_zero_exit",
                f"Return code {result.returncode}; stderr={result.stderr.strip()}",
                run_timestamp,
            )
        if not result.stdout.strip():
            log(f"{solver_name} produced no output", level="WARN")
            return []
        return parse_acnf_output(result.stdout)

    run_results = []
    clauses = []
    for query_idx, query in enumerate(queries):
        clauses.extend(query["clauses"])
        with open(local_wcnf_path, "w", encoding="utf-8") as temp_file:
            for clause in clauses:
                temp_file.write(f"h {' '.join(map(str, clause))} 0\n")
            for assumption in query["assumptions"]:
                temp_file.write(f"h {assumption} 0\n")
            if query["type"] in {"u", "w"}:
                for weight, soft_lit in query["soft_lits"]:
                    temp_file.write(f"{weight} {-int(soft_lit)} 0\n")

        result = run_process([solver_info["path"], local_wcnf_path], timeout=solver_timeout)
        if result.returncode not in EXPECTED_SOLVER_RETURN_CODES:
            record_error(
                error_rows,
                iteration,
                solver_name,
                query_idx,
                "solver_non_zero_exit",
                f"Return code {result.returncode}; stderr={result.stderr.strip()}",
                run_timestamp,
            )

        if not result.stdout.strip():
            record_error(
                error_rows,
                iteration,
                solver_name,
                query_idx,
                "solver_empty_output",
                "Solver produced no output",
                run_timestamp,
            )
            continue

        run_results.append(result.stdout)

    if not run_results:
        return []
    return parse_wcnf_output("\n".join(run_results))


def run_iteration(iteration, args, run_timestamp):
    iteration_errors = []
    status_mismatches = 0
    value_mismatches = 0
    snapshot_path = None

    temp_dir = tempfile.mkdtemp(prefix=f"acnf-simple-{iteration}-")
    local_acnf_path = os.path.join(temp_dir, "temp_acnf.acnf")
    local_wcnf_path = os.path.join(temp_dir, "temp_wcnf.wcnf")

    try:
        queries = generate_acnf(args.acnf_file, local_acnf_path)
        log(f"Iteration {iteration}: generated {len(queries)} queries")

        solver_results = {}
        for solver_name, solver_info in SOLVERS.items():
            log(f"Iteration {iteration}: running {solver_name}")
            try:
                parsed = run_solver_for_queries(
                    solver_name,
                    solver_info,
                    local_acnf_path,
                    local_wcnf_path,
                    queries,
                    args.solver_timeout,
                    iteration,
                    iteration_errors,
                    run_timestamp,
                )
                solver_results[solver_name] = parsed
                if len(parsed) != len(queries):
                    record_error(
                        iteration_errors,
                        iteration,
                        solver_name,
                        -1,
                        "result_count_mismatch",
                        f"Got {len(parsed)} results, expected {len(queries)}",
                        run_timestamp,
                    )
            except subprocess.TimeoutExpired:
                record_error(
                    iteration_errors,
                    iteration,
                    solver_name,
                    -1,
                    "solver_timeout",
                    f"Timed out after {args.solver_timeout}s",
                    run_timestamp,
                )
                solver_results[solver_name] = []

        status_mismatches, value_mismatches = compare_solver_results_per_iteration(
            queries,
            solver_results,
            iteration,
            iteration_errors,
            run_timestamp,
        )

        for solver_name, output in solver_results.items():
            validate_model_and_costs(queries, solver_name, output, iteration, iteration_errors, run_timestamp)

        if iteration_errors:
            snapshot_path = save_bugged_acnf_snapshot(local_acnf_path, args.bugged_acnf_dir, iteration, run_timestamp)
            append_error_rows_to_csv(args.error_log_csv, iteration_errors)
            log(
                f"Iteration {iteration}: wrote {len(iteration_errors)} errors to {args.error_log_csv}",
                level="WARN",
            )
            if snapshot_path:
                log(f"Iteration {iteration}: saved ACNF snapshot to {snapshot_path}", level="WARN")
        else:
            log(f"Iteration {iteration}: no errors found")

        return {
            "status_mismatches": status_mismatches,
            "value_mismatches": value_mismatches,
            "error_count": len(iteration_errors),
            "snapshot_path": snapshot_path,
        }
    finally:
        try:
            if os.path.exists(local_wcnf_path):
                os.remove(local_wcnf_path)
            if os.path.exists(local_acnf_path) and args.acnf_file is None:
                os.remove(local_acnf_path)
            os.rmdir(temp_dir)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="Simple ACNF fuzz runner: generation, solver runs, comparison, and error logging"
    )
    parser.add_argument("--iterations", type=int, default=1, help="Number of sequential iterations")
    parser.add_argument("--acnf-file", type=str, default=None, help="Use an existing ACNF instead of generating one")
    parser.add_argument("--solver-timeout", type=float, default=300.0, help="Per solver call timeout in seconds")
    parser.add_argument("--error-log-csv", type=str, default="error_log.csv", help="Error CSV output path")
    parser.add_argument("--bugged-acnf-dir", type=str, default="BuggedACNFs", help="Directory for bugged ACNF snapshots")
    args = parser.parse_args()

    if args.iterations <= 0:
        raise SystemExit("--iterations must be greater than 0")
    if args.solver_timeout <= 0:
        raise SystemExit("--solver-timeout must be greater than 0")

    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log(f"Run timestamp: {run_timestamp}")

    total_status_mismatches = 0
    total_value_mismatches = 0
    total_errors = 0

    for iteration in range(1, args.iterations + 1):
        result = run_iteration(iteration, args, run_timestamp)
        total_status_mismatches += result["status_mismatches"]
        total_value_mismatches += result["value_mismatches"]
        total_errors += result["error_count"]

    log("=== FINAL SUMMARY ===")
    log(f"Iterations: {args.iterations}")
    log(f"Total status mismatches: {total_status_mismatches}")
    log(f"Total value mismatches: {total_value_mismatches}")
    log(f"Total error rows written: {total_errors}")


if __name__ == "__main__":
    main()