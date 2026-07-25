from __future__ import annotations

import importlib.util
from typing import Optional

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.core.ipamir_subprocess_replay_base import OneShotSubprocessReplaySolverBase


class TTOpenWBOInc(OneShotSubprocessReplaySolverBase):
    """TT-Open-WBO-Inc fake-incremental wrapper with one-shot subprocess isolation."""

    pass_assumptions_to_worker = False
    nonunit_soft_policy = "store"
    # TT OpenWBO-Inc may terminate the worker process with SAT-style exit codes
    # (not IPAMIR status codes), so we must remap fallback code 10 to OPTIMUM.
    compat_exit_code_status_map = {
        10: SolveStatus.OPTIMUM,
        20: SolveStatus.UNSAT,
        30: SolveStatus.OPTIMUM,
        40: SolveStatus.ERROR,
        50: SolveStatus.UNKNOWN,
    }

    @property
    def worker_solver_class_path(self) -> str:
        return "hermax.core.tt_openwbo_inc_py.tt_openwbo_inc_solver.TTOpenWBOIncSolver"

    @property
    def default_signature(self) -> str:
        return "TT-Open-WBO-Inc (subprocess wrapper)"

    @property
    def timeout_error_prefix(self) -> str:
        return "TT-Open-WBO-Inc"

    @classmethod
    def is_available(cls) -> bool:
        if importlib.util.find_spec("hermax.core.tt_openwbo_inc") is None:
            return False
        mod_name = "hermax.core.tt_openwbo_inc_py.tt_openwbo_inc_solver"
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
