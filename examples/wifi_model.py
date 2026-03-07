import argparse
import random
import time

from hermax.model import Clause, Model
from wifi_lib import (
    HAS_VISUALIZATION,
    generate_congestion_weights,
    generate_random_network,
    visualize_network,
)


def build_wifi_model(routers, edges, freqs, weights, w_offline, *, allow_offline=False, forced=None):
    model = Model()

    routers_list = sorted(routers)
    freq_list = sorted(freqs)
    freq_labels = {f: str(f) for f in freq_list}
    state = model.enum_dict(
        "router_state",
        keys=routers_list,
        choices=[freq_labels[f] for f in freq_list],
        nullable=allow_offline,
    )

    def force_offline(r):
        # Nullable enum uses "all choices false" for offline / None.
        lits = [~(state[r] == freq_labels[f]) for f in freq_list]
        out = lits[0]
        for lit in lits[1:]:
            out &= lit
        return out

    # Interference edges: adjacent routers cannot share the same real frequency.
    for u, v in edges:
        for f in freq_list:
            model &= (~(state[u] == freq_labels[f]) | ~(state[v] == freq_labels[f]))

    # Soft costs: pay congestion weight if router uses frequency f.
    # In unit-soft-literal semantics, `obj += ~x(r,f)` pays when x(r,f) is True.
    for r in routers_list:
        for f in freq_list:
            model.obj[weights[(r, f)]] += ~(state[r] == freq_labels[f])
        if allow_offline:
            # Pay offline penalty when no real frequency is selected (nullable enum == None).
            model.obj[w_offline] += Clause.from_iterable([(state[r] == freq_labels[f]) for f in freq_list])

    # Optional event-specific hard assignments (scratch-mode equivalent of assumptions).
    for lit in forced or ():
        model &= lit

    return model, state, routers_list, freq_list, force_offline


def extract_assignment_from_model_result(result, state, routers_list):
    values = result[state]
    out = {}
    for r in routers_list:
        chosen = values[r]
        out[r] = 0 if chosen is None else int(chosen)
    return out


def pick_random_event(routers, freqs, *, allow_offline=False):
    event_type = random.choice(["spike", "lock", "offline", "none"])
    forced = []
    event_desc = "none"

    if event_type == "offline" and allow_offline:
        r = random.choice(sorted(routers))
        forced = [("offline", r, None)]
        event_desc = f"offline(router={r})"
    elif event_type == "lock":
        r = random.choice(sorted(routers))
        f = random.choice(sorted(freqs))
        forced = [("lock", r, f)]
        event_desc = f"lock(router={r}, freq={f})"
    elif event_type == "spike":
        event_desc = "spike"
    return event_type, forced, event_desc


def apply_spike(weights, routers, freqs):
    for r in routers:
        f = random.choice(sorted(freqs))
        weights[(r, f)] = random.randint(100, 500)


def main():
    parser = argparse.ArgumentParser(description="WiFi Frequency Assignment Benchmark (hermax.model version)")
    parser.add_argument("--nodes", type=int, default=20, help="Number of routers")
    parser.add_argument("--edge-prob", type=float, default=0.25, help="Probability of interference between nodes")
    parser.add_argument("--freqs", type=int, default=6, help="Number of available frequencies")
    parser.add_argument("--iterations", type=int, default=3, help="Number of random events to simulate")
    parser.add_argument(
        "--allow-offline",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Allow routers to be assigned offline state 0 (default: disabled)",
    )
    parser.add_argument("--image", action="store_true", help="Generate network graphs (requires networkx/matplotlib)")
    parser.add_argument("--debug", action="store_true", help="Enable verbose output")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    if args.image and not HAS_VISUALIZATION:
        print("Warning: --image requested but networkx or matplotlib is missing. Skipping images.")

    random.seed(args.seed)
    routers, edges = generate_random_network(args.nodes, args.edge_prob)
    freqs = set(range(1, args.freqs + 1))
    weights = generate_congestion_weights(routers, freqs, 5, 30)
    w_offline = 9999

    total_build_s = 0.0
    total_solve_s = 0.0
    solved = 0

    print("--- Starting Benchmark: MODEL (scratch rebuild) mode ---")

    for iteration in range(1, args.iterations + 1):
        event_type, forced_pairs, event_desc = pick_random_event(routers, freqs, allow_offline=args.allow_offline)
        if event_type == "spike":
            apply_spike(weights, routers, freqs)

        t0 = time.perf_counter()
        model, state, routers_list, _freq_list, force_offline = build_wifi_model(
            routers,
            edges,
            freqs,
            weights,
            w_offline,
            allow_offline=args.allow_offline,
            forced=[],
        )
        # Translate event literals after the matrix exists.
        for kind, r, f in forced_pairs:
            if kind == "lock":
                model &= (state[r] == str(f))
            elif kind == "offline":
                model &= force_offline(r)
        t1 = time.perf_counter()

        res = model.solve()
        t2 = time.perf_counter()

        total_build_s += (t1 - t0)
        total_solve_s += (t2 - t1)
        solved += 1

        print(f"\n--- Event Iteration {iteration} ---")
        if args.debug:
            print(f"[DEBUG] event={event_desc}")
        print(f"Solve Time: {t2 - t1:.4f} seconds | Feasible: {res.ok}")

        if res.ok:
            print(f"Cost: {res.cost}")
            if args.debug or args.image:
                assignment = extract_assignment_from_model_result(res, state, routers_list)
                if args.debug:
                    print(f"[DEBUG] Assignment: {assignment}")
                if args.image:
                    visualize_network(routers, edges, assignment, iteration)
        else:
            print(f"Status: {res.status}")

    print("\n=== Benchmark Results ===")
    print("Mode:            MODEL (scratch rebuild)")
    print(f"Total Queries:   {solved}")
    if solved:
        print(f"Avg Solve Time:  {total_solve_s / solved:.5f} s")
        print(f"Total Solve Time:{total_solve_s:.4f} s")
        print(f"Total Build Time:{total_build_s:.4f} s (DSL construction + export)")


main()
