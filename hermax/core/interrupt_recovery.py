"""Internal capability for native solvers that can rebuild after interruption."""

from __future__ import annotations

import abc


class InterruptRecovery(abc.ABC):
    """Optional Hermax capability; not part of the IPAMIR contract."""

    @abc.abstractmethod
    def set_rebuild_on_interrupt(self, enabled: bool = True) -> None:
        """Configure native-state recovery after an interrupted solve."""

