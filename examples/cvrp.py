import math
from dataclasses import dataclass
from typing import Dict, Tuple

# Assuming your API is in a module named hermax_api
from hermax.model import Model, SoftRef, BoolMatrix, IntVector

@dataclass(frozen=True)
class CVRPInstance:
    demands: list[int]
    capacity: int
    num_vehicles: int
    distances: list[list[int]]

    @property
    def N(self) -> int:
        return len(self.demands)

def encode_cvrp(
    m: Model, inst: CVRPInstance
) -> Tuple[BoolMatrix, IntVector, Dict[Tuple[int, int], SoftRef]]:
    
    edges = m.bool_matrix("edge", inst.N, inst.N)
    loads = m.int_vector("load", inst.N, lb=0, ub=inst.capacity + 1)
    
    m &= sum(edges.row(0)) == inst.num_vehicles
    m &= sum(edges.col(0)) == inst.num_vehicles
    m &= loads[0] == 0

    edge_refs = {}

    for i in range(inst.N):
        m &= ~edges[i][i]
        
        if i > 0:
            m &= edges.row(i).exactly_one()
            m &= edges.col(i).exactly_one()
            m &= loads[i] >= inst.demands[i]

        for j in range(1, inst.N):
            if i != j:
                m &= (loads[i] + inst.demands[j] <= loads[j]).only_if(edges[i][j])
                
        for j in range(inst.N):
            if i != j:
                # Store SoftRefs to allow dynamic weight updates later
                edge_refs[(i, j)] = m.add_soft(~edges[i][j], weight=inst.distances[i][j])

    return edges, loads, edge_refs

def print_solution(title: str, res, edges: BoolMatrix, loads: IntVector, N: int):
    print(f"\n=== {title} ===")
    if not res.ok:
        print("Status: UNSAT or Failed")
        return
    
    print(f"Optimal Cost: {res.cost}")
    for i in range(N):
        for j in range(N):
            if res[edges[i][j]]:
                print(f"  Route: {i} -> {j} | Load after {j}: {res[loads[j]]}")

def run_paper_example():
    coords = [(0, 0), (2, 4), (5, 2), (7, 6), (1, 5)]
    distances = [
        [int(math.hypot(a[0]-b[0], a[1]-b[1]) * 10) for b in coords] 
        for a in coords
    ]
    
    inst = CVRPInstance(
        demands=[0, 4, 5, 3, 5], 
        capacity=10, 
        num_vehicles=2, 
        distances=distances
    )

    m = Model()
    edges, loads, edge_refs = encode_cvrp(m, inst)

    # 1. Base Solve
    res1 = m.solve(backend="maxsat")
    print_solution("Base CVRP", res1, edges, loads, inst.N)

    # 2. Incrementality via Assumptions (Temporary)
    # Force the route 1 -> 3 for this solve only.
    res2 = m.solve(assumptions=[edges[1][3]])
    print_solution("Assumption: Force Route 1 -> 3", res2, edges, loads, inst.N)

    # 3. Incrementality via Weight Updates (Permanent)
    # Traffic spikes between 0 and 1, drastically increasing its cost weight.
    m.update_soft_weight(edge_refs[(0, 1)], new_weight=999)
    res3 = m.solve()
    print_solution("Weight Update: Edge 0 -> 1 Avoided", res3, edges, loads, inst.N)

if __name__ == "__main__":
    run_paper_example()