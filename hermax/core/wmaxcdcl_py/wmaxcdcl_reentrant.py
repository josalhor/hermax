from .wmaxcdcl_solver import WMaxCDCLSolver


class WMaxCDCLReentrant(WMaxCDCLSolver):
    """
    Reentrant WMaxCDCL wrapper.

    This is a rebuild-per-solve wrapper (same implementation strategy as the
    fake-incremental wrapper) exposed under a non-incremental/reentrant name.
    """

    def signature(self) -> str:
        return "WMaxCDCL (reentrant rebuild wrapper)"

