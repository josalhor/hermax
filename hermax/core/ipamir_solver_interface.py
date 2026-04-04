"""
Core Python interface for IPAMIR-style incremental MaxSAT solvers.

This module defines a common contract used by Hermax wrappers around distinct
MaxSAT backends. The contract follows the incremental MaxSAT API model
introduced in:

- Andreas Niskanen, Jeremias Berg, Matti Järvisalo.
  "Incremental Maximum Satisfiability", SAT 2022.

and is aligned with incremental SAT interface conventions:

- Tomas Balyo, Armin Biere. "IPASIR: The Standard Interface for Incremental
  Satisfiability Solving".
"""

import abc
from enum import IntEnum
from typing import List, Optional, Callable


class SolveStatus(IntEnum):
    """Solver status codes, aligned with IPAMIR C API."""
    INTERRUPTED = 0   # Interrupted without a feasible solution
    INTERRUPTED_SAT = 10          # Interrupted with a feasible solution (not proven optimal)
    UNSAT = 20        # Proven unsatisfiable
    OPTIMUM = 30      # Proven optimal
    ERROR = 40        # Solver in an error state
    UNKNOWN = 60      # Internal state before first solve


def is_feasible(st: SolveStatus) -> bool:
    """Returns True if the status code indicates a feasible solution was found."""
    return st in (SolveStatus.INTERRUPTED_SAT, SolveStatus.OPTIMUM)


def is_final(st: SolveStatus) -> bool:
    """Returns True if the status code indicates the search was definitive (UNSAT or OPTIMUM)."""
    return st in (SolveStatus.UNSAT, SolveStatus.OPTIMUM)


class IPAMIRSolver(abc.ABC):
    """
    Abstract Base Class for IPAMIR-compatible solvers.

    This interface is a Pythonic adaptation of the IPAMIR (Incremental
    Parameterizable MaxSAT Interface) C API. It defines the core methods
    required for incremental MaxSAT solving, including:

    - adding hard clauses (`add_clause`)
    - defining/updating soft literals (`set_soft`, `add_soft_unit`)
    - solving under temporary assumptions (`solve(assumptions=...)`)
    - querying status/cost/model after each call

    The interface intentionally exposes solver-agnostic primitives; different
    concrete backends may implement different internal state reuse policies
    while preserving this external contract.
    """

    def __init__(self, *args, **kwargs):
        self._status: SolveStatus = SolveStatus.UNKNOWN

    @abc.abstractmethod
    def add_clause(self, clause: list[int]) -> None:
        """
        Adds a hard clause to the solver.

        A hard clause must be satisfied in every model. If an empty clause is
        added, the formula becomes UNSAT.

        Example:
            solver.add_clause([-1, 2])
        """
        ...

    @abc.abstractmethod
    def set_soft(self, lit: int, weight: int) -> None:
        """
        Declares or updates a soft literal.

        A soft literal penalizes its *positive* assignment if the literal is negative
        (and vice versa). For example, `set_soft(-1, 10)` means variable 1 = True
        adds cost 10.

        Example:
            solver.set_soft(-1, 5)
        """
        ...

    @abc.abstractmethod
    def add_soft_unit(self, lit: int, weight: int) -> None:
        """
        Shortcut for `add_soft_relaxed([lit], weight, relax_var=None)`.

        Adds a soft *unit* clause. This is equivalent to:
            - adding a hard clause [lit]
            - associating a weight that penalizes its violation.

        Example:
            solver.add_soft_unit(-1, 10)
        """
        ...

    
    def add_soft_relaxed(
        self,
        clause: list[int],
        weight: int,
        relax_var: int | None,
    ):
        """
        Adds a non-unit soft clause, with explicit control over the relaxation variable.

        * `clause` is the list of literals in the base constraint.
        * `weight` is the cost if the clause is violated.
        * `relax_var` is the variable used to relax the clause:

          - If `None` and clause is *unit*, the solver automatically handles it.
          - If `None` and clause has more than one literal, this is invalid and
            must raise an error.
          - If given, the solver will add the hard clause `(clause ∨ relax_var)`
            and associate a soft unit clause `(-relax_var)` with the specified weight.

        Example:
            # Non-unit soft clause: (-1 ∨ -2) with cost 5 and relaxation var 3
            solver.add_soft_relaxed([-1, -2], 5, relax_var=3)
        """
        # validate
        if not isinstance(clause, list) or len(clause) == 0:
            raise ValueError("clause must be a non-empty list")
        if not isinstance(weight, int) or weight <= 0:
            raise ValueError("weight must be a positive int")

        if relax_var is None:
            if len(clause) != 1:
                raise ValueError("relax_var=None only allowed for unit clauses")
            self.add_soft_unit(int(clause[0]), int(weight))
            return None

        # explicit relax var path: hard (clause ∪ {+b}), soft [-b]
        b = abs(int(relax_var))
        new_hard = [*map(int, clause), b]
        self.add_clause(new_hard)
        self.set_soft(-b, int(weight))
        return b

    @abc.abstractmethod
    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False
    ) -> bool:
        """
        Solve the formula under the given assumptions.

        Args:
            assumptions: A list of literals to be used as assumptions for this solve call.
                         These are cleared after the solve.
            raise_on_abnormal: If True, raises a RuntimeError on status INTERRUPTED or ERROR.

        Returns:
            True if a feasible solution is found (status is SAT or OPTIMUM).
            False if the formula is UNSAT or the solve was interrupted without a solution.
        """
        ...

    @abc.abstractmethod
    def get_status(self) -> SolveStatus:
        """Return last solver status."""
        ...

    @abc.abstractmethod
    def get_cost(self) -> int:
        """
        Objective value of the last solution.
        Raises RuntimeError if status is not SAT or OPTIMUM.
        """
        ...

    @abc.abstractmethod
    def val(self, lit: int) -> int:
        """
        Return -1, 0, or +1 value of a literal in the last model.

        * -1: literal is false
        *  0: literal is unassigned/don't care
        * +1: literal is true

        Raises RuntimeError if no model is available.
        """
        ...

    @abc.abstractmethod
    def get_model(self) -> Optional[List[int]]:
        """
        Return full model as a list of signed integers, or None.
        Raises RuntimeError if status is not SAT or OPTIMUM.
        """
        ...

    @abc.abstractmethod
    def signature(self) -> str:
        """Return solver signature string (name, version)."""
        ...

    @abc.abstractmethod
    def close(self) -> None:
        """Release underlying resources."""
        ...

    # ---- Optional features ----

    def new_var(self) -> int:
        """Allocate a fresh variable id. Optional."""
        raise NotImplementedError("new_var is not implemented by this solver.")

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        """Register callback. Optional."""
        raise NotImplementedError("set_terminate is not implemented by this solver.")

    def set_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """Register a generic callback. Optional."""
        try:
            self.set_terminate(callback)
        except NotImplementedError:
            raise NotImplementedError("set_callback is not implemented by this solver.")
