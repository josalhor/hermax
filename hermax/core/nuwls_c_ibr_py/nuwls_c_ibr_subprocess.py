from __future__ import annotations

import importlib.util
from typing import Optional

from pysat.formula import WCNF

from hermax.core.ipamir_subprocess_replay_base import OneShotSubprocessReplaySolverBase


class NuWLSCIBR(OneShotSubprocessReplaySolverBase):
    """NuWLS-c-IBR fake-incremental wrapper with one-shot subprocess isolation."""

    pass_assumptions_to_worker = True
    nonunit_soft_policy = "relax"

    @property
    def worker_solver_class_path(self) -> str:
        return "hermax.core.nuwls_c_ibr_py.nuwls_c_ibr_solver.NuWLSCIBRSolver"

    @property
    def default_signature(self) -> str:
        return "NuWLS-c-IBR (subprocess wrapper)"

    @property
    def timeout_error_prefix(self) -> str:
        return "NuWLS-c-IBR"

    @classmethod
    def is_available(cls) -> bool:
        if importlib.util.find_spec("hermax.core.nuwls_c_ibr") is None:
            return False
        mod_name = "hermax.core.nuwls_c_ibr_py.nuwls_c_ibr_solver"
        return importlib.util.find_spec(mod_name) is not None

    def __init__(
        self,
        formula: Optional[WCNF] = None,
        *args,
        default_time_limit: Optional[float] = None,
        time_limit_grace: float = 1.0,
        timeout_s: Optional[float] = None,
        timeout_grace_s: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(
            formula=formula,
            *args,
            default_time_limit=default_time_limit,
            time_limit_grace=time_limit_grace,
            timeout_s=timeout_s,
            timeout_grace_s=timeout_grace_s,
            **kwargs,
        )
