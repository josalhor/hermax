from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _lit_true(lit: int, assignment: dict[int, bool]) -> bool:
    var = abs(lit)
    val = assignment.get(var, False)
    return val if lit > 0 else (not val)


@dataclass
class WeightedCNF:
    hard: list[list[int]]
    soft: list[tuple[list[int], int]]
    nvars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "hard": self.hard,
            "soft": [[cl, w] for cl, w in self.soft],
            "nvars": self.nvars,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WeightedCNF":
        hard = [[int(x) for x in cl] for cl in payload.get("hard", [])]
        soft = [([int(x) for x in cl], int(w)) for cl, w in payload.get("soft", [])]
        nvars = int(payload.get("nvars", 0))
        if nvars <= 0:
            nvars = 0
            for cl in hard:
                for lit in cl:
                    nvars = max(nvars, abs(int(lit)))
            for cl, _w in soft:
                for lit in cl:
                    nvars = max(nvars, abs(int(lit)))
        return cls(hard=hard, soft=soft, nvars=nvars)

    def validate(self) -> None:
        for cl in self.hard:
            for lit in cl:
                if int(lit) == 0:
                    raise ValueError("Literal 0 is invalid in hard clause")
        for cl, w in self.soft:
            if int(w) <= 0:
                raise ValueError("Soft weight must be positive")
            for lit in cl:
                if int(lit) == 0:
                    raise ValueError("Literal 0 is invalid in soft clause")

    def to_wcnf(self) -> str:
        self.validate()
        top = sum(w for _cl, w in self.soft) + 1
        lines = [f"p wcnf {self.nvars} {len(self.hard) + len(self.soft)} {top}"]
        for cl in self.hard:
            lines.append(f"{top} " + " ".join(str(x) for x in cl) + " 0")
        for cl, w in self.soft:
            lines.append(f"{w} " + " ".join(str(x) for x in cl) + " 0")
        return "\n".join(lines) + "\n"

    @staticmethod
    def assignment_from_model(model: list[int] | None) -> dict[int, bool]:
        out: dict[int, bool] = {}
        if not model:
            return out
        for signed in model:
            v = abs(int(signed))
            out[v] = int(signed) > 0
        return out

    def hard_satisfied(self, model: list[int] | None) -> bool:
        assignment = self.assignment_from_model(model)
        for cl in self.hard:
            if not cl:
                return False
            if not any(_lit_true(lit, assignment) for lit in cl):
                return False
        return True

    def soft_cost(self, model: list[int] | None) -> int:
        assignment = self.assignment_from_model(model)
        total = 0
        for cl, w in self.soft:
            if not cl:
                total += int(w)
                continue
            if not any(_lit_true(lit, assignment) for lit in cl):
                total += int(w)
        return total

