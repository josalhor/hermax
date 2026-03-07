from .spb_maxsat_c_fps_solver import SPBMaxSATCFPSSolver


class SPBMaxSATCFPSReentrant(SPBMaxSATCFPSSolver):
    def signature(self) -> str:
        return "SPB-MaxSAT-c-FPS (NuWLS-c / BLS, native reentrant rebuild wrapper)"

