from __future__ import annotations

import random
from dataclasses import dataclass

from .model import WeightedCNF


@dataclass
class WCNFuzzConfig:
    min_layers: int = 2
    max_layers: int = 10
    min_vars_per_layer: int = 3
    max_vars_per_layer: int = 12


class WCNFuzz:
    def __init__(self, rng: random.Random, cfg: WCNFuzzConfig | None = None):
        self.rng = rng
        self.cfg = cfg or WCNFuzzConfig()

    def _sample_wmax(self) -> int:
        p = self.rng.random()
        if p < 0.20:
            return 1
        if p < 0.40:
            return self.rng.randint(2, 32)
        if p < 0.60:
            return self.rng.randint(33, 256)
        if p < 0.80:
            return self.rng.randint(257, 65535)
        if p < 0.96:
            return self.rng.randint(65536, 2**32)
        return self.rng.randint(2**32 + 1, 2**63 - 1)

    def _sample_clause_size(self) -> int:
        p = self.rng.random()
        if p < 0.10:
            return 2
        if p < 0.76:
            return 3
        if p < 0.88:
            return 1
        return 4

    def _weighted_var_pool(self, layer_vars: list[list[int]], layer_idx: int) -> list[int]:
        bag: list[int] = []
        for j in range(layer_idx + 1):
            decay = 0.5 ** (layer_idx - j)
            reps = max(1, int(8 * decay))
            bag.extend(layer_vars[j] * reps)
        return bag

    def _sample_clause(self, var_pool: list[int], size: int) -> list[int]:
        clause: list[int] = []
        seen: set[int] = set()
        attempts = 0
        target = max(1, size)
        while len(clause) < target and attempts < 100:
            attempts += 1
            v = self.rng.choice(var_pool)
            if v in seen:
                continue
            seen.add(v)
            sign = -1 if self.rng.random() < 0.5 else 1
            clause.append(sign * v)
        if not clause:
            v = abs(self.rng.choice(var_pool))
            clause.append(v)
        return clause

    def _inject_gate(
        self,
        gate_kind: str,
        var_pool: list[int],
        next_var: int,
        layer_type: str,
        hard: list[list[int]],
        soft: list[tuple[list[int], int]],
        wmax: int,
    ) -> int:
        def add_clause_target(cl: list[int]) -> None:
            if layer_type == "hard":
                hard.append(cl)
            else:
                soft.append((cl, self.rng.randint(1, max(1, wmax))))

        out = next_var
        next_var += 1

        if gate_kind == "EQ":
            a = abs(self.rng.choice(var_pool))
            clauses = [[-out, a], [out, -a]]
        elif gate_kind == "AND":
            a = abs(self.rng.choice(var_pool))
            b = abs(self.rng.choice(var_pool))
            clauses = [[-out, a], [-out, b], [out, -a, -b]]
        elif gate_kind == "XOR3":
            xs = [abs(self.rng.choice(var_pool)) for _ in range(3)]
            # Lightweight parity stress encoding (not minimal, intentionally noisy)
            clauses = [
                [out, xs[0], xs[1], xs[2]],
                [out, -xs[0], -xs[1], xs[2]],
                [out, -xs[0], xs[1], -xs[2]],
                [out, xs[0], -xs[1], -xs[2]],
                [-out, -xs[0], -xs[1], -xs[2]],
                [-out, xs[0], xs[1], -xs[2]],
                [-out, xs[0], -xs[1], xs[2]],
                [-out, -xs[0], xs[1], xs[2]],
            ]
        else:  # XOR4
            xs = [abs(self.rng.choice(var_pool)) for _ in range(4)]
            clauses = []
            for mask in range(16):
                lits = []
                parity = 0
                for i, x in enumerate(xs):
                    bit = (mask >> i) & 1
                    parity ^= bit
                    lits.append(-x if bit else x)
                clauses.append(([out] if parity else [-out]) + lits)

        if self.rng.random() < 0.75:
            act = next_var
            next_var += 1
            clauses = [cl + [act] for cl in clauses]
            soft.append(([-act], self.rng.randint(1, max(1, wmax))))

        for cl in clauses:
            add_clause_target(cl)

        return next_var

    def generate(self) -> WeightedCNF:
        layers = self.rng.randint(self.cfg.min_layers, self.cfg.max_layers)
        layer_vars: list[list[int]] = []
        hard: list[list[int]] = []
        soft: list[tuple[list[int], int]] = []

        next_var = 1
        for li in range(layers):
            nv = self.rng.randint(self.cfg.min_vars_per_layer, self.cfg.max_vars_per_layer)
            vars_here = list(range(next_var, next_var + nv))
            next_var += nv
            layer_vars.append(vars_here)

            layer_type = "hard" if (li == 0 or self.rng.random() < 0.5) else "soft"
            r = self.rng.uniform(1.0, 2.5) if layer_type == "hard" else self.rng.uniform(3.5, 5.5)
            target_clauses = max(1, int(r * nv))
            wmax = self._sample_wmax()
            pool = self._weighted_var_pool(layer_vars, li)

            for _ in range(target_clauses):
                k = self._sample_clause_size()
                cl = self._sample_clause(pool, k)
                if layer_type == "hard":
                    hard.append(cl)
                else:
                    soft.append((cl, self.rng.randint(1, max(1, wmax))))

            gate_budget = max(1, nv // 4)
            for _ in range(gate_budget):
                gk = self.rng.choice(["EQ", "AND", "XOR3", "XOR4"])
                next_var = self._inject_gate(gk, pool, next_var, layer_type, hard, soft, wmax)

        # Ensure at least one hard and one soft where possible
        if not hard and soft:
            hard.append([1])
        if not soft and hard:
            v = abs(hard[0][0]) if hard and hard[0] else 1
            soft.append(([-v], 1))

        wcnf = WeightedCNF(hard=hard, soft=soft, nvars=max(1, next_var - 1))
        wcnf.validate()
        return wcnf

