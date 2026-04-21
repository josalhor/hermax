from __future__ import annotations

import importlib.util
from typing import Optional

from pysat.formula import WCNF

from hermax.core.ipamir_subprocess_replay_base import OneShotSubprocessReplaySolverBase


class Loandra(OneShotSubprocessReplaySolverBase):
    """Loandra fake-incremental wrapper with one-shot subprocess isolation."""

    pass_assumptions_to_worker = False

    @property
    def worker_solver_class_path(self) -> str:
        return "hermax.core.loandra_py.loandra_solver.LoandraSolver"

    @property
    def default_signature(self) -> str:
        return "Loandra (subprocess wrapper)"

    @property
    def timeout_error_prefix(self) -> str:
        return "Loandra"

    @classmethod
    def is_available(cls) -> bool:
        if importlib.util.find_spec("hermax.core.loandra") is None:
            return False
        mod_name = "hermax.core.loandra_py.loandra_solver"
        return importlib.util.find_spec(mod_name) is not None

    def __init__(
        self,
        formula: Optional[WCNF] = None,
        *args,
        timeout_s: float = 30.0,
        timeout_grace_s: float = 1.0,
        **kwargs,
    ):
        super().__init__(
            formula=formula,
            *args,
            timeout_s=timeout_s,
            timeout_grace_s=timeout_grace_s,
            **kwargs,
        )
