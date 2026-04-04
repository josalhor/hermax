import importlib.util
import itertools
import random
from pysat.formula import IDPool

from hermax.incremental import UWrMaxSATCompetition as UWrMaxSAT


HAS_VISUALIZATION = (
    importlib.util.find_spec("networkx") is not None
    and importlib.util.find_spec("matplotlib.pyplot") is not None
)


def generate_random_network(num_routers: int, edge_prob: float):
    return generate_random_network_with_rng(num_routers, edge_prob, rng=random.Random(0))


def generate_random_network_with_rng(num_routers: int, edge_prob: float, *, rng):
    routers = set(range(1, num_routers + 1))
    edges = set()
    for u, v in itertools.combinations(sorted(routers), 2):
        if rng.random() < edge_prob:
            edges.add((u, v))
    return routers, edges


def generate_congestion_weights(routers: set, freqs: set, min_w: int, max_w: int):
    return generate_congestion_weights_with_rng(routers, freqs, min_w, max_w, rng=random.Random(0))


def generate_congestion_weights_with_rng(routers: set, freqs: set, min_w: int, max_w: int, *, rng):
    weights = {}
    for r in sorted(routers):
        for f in sorted(freqs):
            weights[(r, f)] = rng.randint(min_w, max_w)
    return weights


def build_var_map(routers, freqs, allow_offline=False):
    states = freqs | ({0} if allow_offline else set())
    vpool = IDPool(start_from=1)
    var_map = {}
    for r in sorted(routers):
        for f in sorted(states):
            var_map[(r, f)] = vpool.id(f"router{r}@freq{f}")
    return var_map


def build_solver_from_scratch(routers, edges, freqs, weights, w_offline, var_map, allow_offline=False):
    solver = UWrMaxSAT()
    states = freqs | ({0} if allow_offline else set())

    def x(r, f):
        return var_map[(r, f)]

    for r in sorted(routers):
        solver.add_clause([x(r, f) for f in sorted(states)])
        for f1, f2 in itertools.combinations(sorted(states), 2):
            solver.add_clause([-x(r, f1), -x(r, f2)])

    for u, v in sorted(edges):
        for f in sorted(freqs):
            solver.add_clause([-x(u, f), -x(v, f)])

    for r in sorted(routers):
        for f in sorted(freqs):
            solver.set_soft(-x(r, f), weight=weights[(r, f)])
        if allow_offline:
            solver.set_soft(-x(r, 0), weight=w_offline)

    return solver


def extract_assignment(model, routers, freqs, var_map, allow_offline=False):
    if not model:
        return {}
    states = freqs | ({0} if allow_offline else set())
    assignment = {}
    for r in sorted(routers):
        for f in sorted(states):
            if var_map[(r, f)] in model or (
                var_map[(r, f)] - 1 < len(model) and model[var_map[(r, f)] - 1] > 0
            ):
                assignment[r] = f
    return assignment


def visualize_network(routers, edges, assignment, iteration):
    if not HAS_VISUALIZATION:
        return

    import matplotlib.pyplot as plt
    import networkx as nx

    graph = nx.Graph()
    graph.add_nodes_from(routers)
    graph.add_edges_from(edges)

    colors = []
    for node in graph:
        freq = assignment.get(node, 0)
        if freq == 0:
            colors.append("lightgray")
        elif freq == 1:
            colors.append("lightcoral")
        elif freq == 2:
            colors.append("lightblue")
        elif freq == 3:
            colors.append("lightgreen")
        else:
            colors.append("gold")

    plt.figure(figsize=(8, 6))
    pos = nx.spring_layout(graph, seed=42)
    nx.draw(graph, pos, node_color=colors, with_labels=True, node_size=600, font_weight="bold")
    plt.title(f"WiFi Frequency Assignment - Event Iteration {iteration}")
    filename = f"wifi_graph_iter_{iteration}.png"
    plt.savefig(filename)
    plt.close()
    print(f"[Image Generated] Saved to {filename}")
