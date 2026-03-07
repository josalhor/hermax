import argparse
import random
import time
from wifi_lib import (
    HAS_VISUALIZATION,
    build_solver_from_scratch,
    build_var_map,
    extract_assignment,
    generate_congestion_weights,
    generate_random_network,
    visualize_network,
)

def main():
    parser = argparse.ArgumentParser(description="WiFi Frequency Assignment Benchmark")
    parser.add_argument("--nodes", type=int, default=25, help="Number of routers")
    parser.add_argument("--edge-prob", type=float, default=0.25, help="Probability of interference between nodes")
    parser.add_argument("--freqs", type=int, default=6, help="Number of available frequencies")
    parser.add_argument("--mode", choices=['incremental', 'scratch'], default='incremental', help="Execution mode")
    parser.add_argument("--infinite", action='store_true', help="Run randomly generated events in an infinite loop")
    parser.add_argument("--iterations", type=int, default=5, help="Number of events to simulate if not infinite")
    parser.add_argument(
        "--allow-offline",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Allow routers to be assigned offline state 0 (default: disabled)",
    )
    parser.add_argument("--debug", action='store_true', help="Enable verbose debug output")
    parser.add_argument("--image", action='store_true', help="Generate network graphs (requires networkx/matplotlib)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    if args.image and not HAS_VISUALIZATION:
        print("Warning: --image requested but networkx or matplotlib is missing. Skipping images.")

    random.seed(args.seed)
    routers, edges = generate_random_network(args.nodes, args.edge_prob)
    freqs = set(range(1, args.freqs + 1))
    weights = generate_congestion_weights(routers, freqs, 5, 30)
    w_offline = 9999
    states = freqs | ({0} if args.allow_offline else set())

    if args.debug:
        print(f"[DEBUG] Nodes: {routers}")
        print(f"[DEBUG] Edges: {edges}")

    # Variable Mapping
    var_map = build_var_map(routers, freqs, allow_offline=args.allow_offline)

    def x(r, f): return var_map[(r, f)]

    # Metrics
    total_solve_time = 0.0
    total_rebuild_time = 0.0
    queries = 0

    print(f"--- Starting Benchmark: {args.mode.upper()} mode ---")

    # Initial Setup
    solver = None
    if args.mode == 'incremental':
        t_start_build = time.perf_counter()
        solver = build_solver_from_scratch(
            routers, edges, freqs, weights, w_offline, var_map, allow_offline=args.allow_offline
        )
        total_rebuild_time += time.perf_counter() - t_start_build

    try:
        max_iters = float('inf') if args.infinite else args.iterations
        iteration = 0

        while iteration < max_iters:
            iteration += 1
            print(f"\n--- Event Iteration {iteration} ---")
            
            # Generate a random dynamic event
            # event_type = random.choice(["offline", "lock", "spike", "none"])
            event_type = random.choice(["spike"])
            current_assumptions = []

            if event_type == "offline":
                r = random.choice(list(routers))
                current_assumptions.append(x(r, 0))
                if args.debug: print(f"[DEBUG] Event: Router {r} forced OFFLINE")
            
            elif event_type == "lock":
                r = random.choice(list(routers))
                f = random.choice(list(freqs))
                current_assumptions.append(x(r, f))
                if args.debug: print(f"[DEBUG] Event: Router {r} LOCKED to freq {f}")
            
            elif event_type == "spike":
                for r in routers:
                    f = random.choice(list(freqs))
                    new_w = random.randint(100, 500)
                    weights[(r, f)] = new_w
                    if args.debug: print(f"[DEBUG] Event: Congestion SPIKE at Router {r}, Freq {f} (Weight: {new_w})")
                    if args.mode == 'incremental':
                        solver.set_soft(-x(r, f), weight=new_w)

            # Execution
            if args.mode == 'scratch':
                t_start_build = time.perf_counter()
                solver = build_solver_from_scratch(
                    routers, edges, freqs, weights, w_offline, var_map, allow_offline=args.allow_offline
                )
                total_rebuild_time += time.perf_counter() - t_start_build

            # Benchmark strictly the solve step
            t0 = time.perf_counter()
            ok = solver.solve(assumptions=current_assumptions)
            t1 = time.perf_counter()
            
            solve_time = t1 - t0
            total_solve_time += solve_time
            queries += 1

            print(f"Solve Time: {solve_time:.4f} seconds | Feasible: {ok}")
            
            if ok:
                print(f"Cost: {solver.get_cost()}")
                if args.debug or args.image:
                    model = solver.get_model()
                    assignment = extract_assignment(
                        model, routers, freqs, var_map, allow_offline=args.allow_offline
                    )
                    if args.debug:
                        print(f"[DEBUG] Assignment: {assignment}")
                    if args.image:
                        visualize_network(routers, edges, assignment, iteration)
            
            if args.mode == 'scratch':
                solver.close()

    except KeyboardInterrupt:
        print("\n[!] Benchmark interrupted by user.")

    finally:
        if solver and args.mode == 'incremental':
            solver.close()

        print("\n=== Benchmark Results ===")
        print(f"Mode:            {args.mode.upper()}")
        print(f"Total Queries:   {queries}")
        if queries > 0:
            print(f"Avg Solve Time:  {total_solve_time / queries:.5f} s")
            print(f"Total Solve Time:{total_solve_time:.4f} s")
            print(f"Total Setup Time:{total_rebuild_time:.4f} s (Graph building & C++ bridging)")

if __name__ == "__main__":
    main()
