from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .compare import WCNFCompare
from .model import WeightedCNF


@dataclass
class TargetFault:
    solver_id: str
    fault: str
    exit_code: int | None


class DeltaReducer:
    def __init__(self, comparator: WCNFCompare, solvers: list[str], out_dir: Path):
        self.comparator = comparator
        self.solvers = solvers
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _same_fault(self, wcnf: WeightedCNF, target: TargetFault, tag: str) -> tuple[bool, dict]:
        case_json = self.out_dir / f"tmp_{tag}.json"
        case_json.write_text(json.dumps(wcnf.to_dict()), encoding="utf-8")
        probe_run_id = f"{self.comparator.run_id}__probe__{tag}"
        _outs, summary = self.comparator.compare_case(
            wcnf,
            case_json,
            self.solvers,
            run_id_override=probe_run_id,
            emit_fault_logs=False,
        )
        for r in summary["results"]:
            if r["solver"] != target.solver_id:
                continue
            if r["fault"] == target.fault and r["exit_code"] == target.exit_code:
                return True, summary
        return False, summary

    def _reduce_list(self, base: WeightedCNF, target: TargetFault, kind: str) -> WeightedCNF:
        arr = list(base.hard if kind == "hard" else base.soft)
        if not arr:
            return base

        n = 2
        idx_tag = 0
        best = arr
        while len(best) >= 2:
            chunk = max(1, len(best) // n)
            changed = False
            i = 0
            while i < len(best):
                idx_tag += 1
                candidate = best[:i] + best[i + chunk :]
                if not candidate and kind == "hard":
                    i += chunk
                    continue
                cand_wcnf = WeightedCNF(
                    hard=candidate if kind == "hard" else list(base.hard),
                    soft=candidate if kind == "soft" else list(base.soft),
                    nvars=base.nvars,
                )
                ok, _summary = self._same_fault(cand_wcnf, target, f"{kind}_{idx_tag}")
                if ok:
                    best = candidate
                    changed = True
                    n = max(2, n - 1)
                    break
                i += chunk
            if not changed:
                if n >= len(best):
                    break
                n = min(len(best), n * 2)

        return WeightedCNF(
            hard=best if kind == "hard" else list(base.hard),
            soft=best if kind == "soft" else list(base.soft),
            nvars=base.nvars,
        )

    def reduce(self, wcnf: WeightedCNF, target: TargetFault) -> WeightedCNF:
        current = wcnf
        # Greedy dd-style passes: hard then soft, repeat while shrinking.
        while True:
            before = (len(current.hard), len(current.soft))
            current = self._reduce_list(current, target, "hard")
            current = self._reduce_list(current, target, "soft")
            after = (len(current.hard), len(current.soft))
            if after == before:
                break
        return current
