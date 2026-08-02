from typing import Any, Callable, Optional, Tuple, List, TypeAlias, overload

# Type aliases matching C++ binding types
TLit: TypeAlias = int
TLiterals: TypeAlias = List[TLit]
TWLit: TypeAlias = Tuple[int, TLit]
TWLiterals: TypeAlias = List[TWLit]


class Solver:
    """Python wrapper for Aperture solver."""

    def __init__(self, sat_solver: str = ...) -> None:
        """Create a solver instance.

        Args:
            sat_solver: Name of the SAT backend to use. Supported solvers:
                - "topor"
                - "glucose" (default)
                - "cadical"
            
        """
        ...

    def add_clause(self, clause: TLiterals) -> bool:
        """Add a clause to the solver.

        Args:
            clause: The clause (aperture.lits) to add.
        Returns:
            True if the clause was added successfully, False if adding the clause caused a conflict (i.e., the formula is unsatisfiable).
            
        """
        ...

    def solve(self, assumptions: TLiterals = ...) -> bool:
        """Solve the current formula under optional assumptions.

        Args:
            assumptions: The assumptions (aperture.lits) to consider.
        Returns:
            True if the formula is satisfiable under the given assumptions, False otherwise.
        """
        ...

    def get_latest_solve_status(self) -> str:
        """Return the status of the most recent solve query.

        Returns:
            The solver status of the most recent solve query, which can be one of:
            - "SAT"
            - "UNSAT"
            - "UNKNOWN"
            - "ERROR"
            - "GLOBAL_CONTRADICTION"
            
        """
        ...

    def get_latest_solution(self) -> TLiterals:
        """Return the solution (model) of the most recent solve query.
            
        Returns:
            Literals (aperture.lits) representing the model of the most recent solve query. The i-th element of the list corresponds to the assignment of variable i+1, 
            where a positive value indicates True and a negative value indicates False. 
            For example, if the returned list is aperture.lits([1, -2, 3]), 
            it means variable 1 is assigned True, variable 2 is assigned False, and variable 3 is assigned True.
            
        """
        ...

    def new_var(self) -> TLit:
        """Create and return a fresh variable.
            
        Returns:
            A newly created literal representing a fresh variable.
            
        """
        ...

    def max_var(self) -> TLit:
        """Return the highest variable index currently in use.

        Returns:
            The highest variable index currently in use.

        """
        ...

    def lit_value(self, lit: TLit) -> TLit:
        """Return the assignment value for a literal in the latest solution.

        Args:
            lit: The literal for which to query the assignment value.
        Returns:
            The assignment value of the given literal in the latest solution, which can be:
            - A positive integer if the literal is assigned True.
            - A negative integer if the literal is assigned False.

             For example, if lit_value(-1) returns 1, it means that variable 1 is assigned False in the latest solution.
             
             If lit_value(2) returns 2, it means that variable 2 is assigned True in the latest solution.
            
        """
        ...

    def get_verbosity_level(self) -> int:
        """Return the current verbosity level.
            
        Returns:
            The current verbosity level. Higher values indicate more verbose output, while a value of 0 indicates no output:
            - 0: No output
            - 1: Basic information about the solving process
            - 2: Detailed information about the solving process and intermediate solutions
            - 3: Debug-level information
            
        """
        ...

    def set_verbosity_level(self, level: int) -> None:
        """Set the solver verbosity level.

        Args:
            level: The verbosity level to set. Higher values indicate more verbose output, while a value of 0 indicates no output:
            - 0: No output
            - 1: Basic information about the solving process
            - 2: Detailed information about the solving process and intermediate solutions
            - 3: Debug-level information
            
        """
        ...

    def set_enable_output_coloring(self, enable: bool) -> None:
        """Enable or disable colored output.

        Args:
            enable: Whether to enable colored output. 
            When enabled, the solver's output will include ANSI color codes to enhance readability between different types of messages, 
            depending on their verbosity level.
            
        """
        ...

    def get_latest_error_reason(self) -> str:
        """Return the latest error message, if any.
            
        Returns:
            The latest error message generated by the solver, if any. If no errors have occurred, this will return an empty string.
            
        """
        ...

    def set_param(self, param_name: str, value: Any) -> None:
        """Set a named solver parameter.

        Args:
            param_name: The name of the parameter to set.
            value: The value to assign to the parameter.

        """
        ...

    def get_totalizer(self, lits: TLiterals, selector: Optional[TLit], rhs_simplification: Optional[int] = ...) -> TLiterals:
        """Build a totalizer encoding for cardinality constraints.

        Args:
            lits: The literals (aperture.lits) to build the totalizer for.
            selector: An optional selector literal that will be added to all clauses generated by the totalizer. 
                      If None, no selector will be used. 
            rhs_simplification: Simplifies the totalizer (reducing the number of variables and clauses) 
                                based on the right-hand that should be the maximal value that will be bounded by the totalizer
                                (usefull for bounding with < and <= constraints). If None, no simplification will be applied.
        Returns:
            Literals (aperture.lits) that encodes the unary sum of the totalizer.
            
        """
        ...

    def get_gen_totalizer(self, wlits: TWLiterals, selector: Optional[TWLit], rhs_simplification: Optional[int] = ...) -> TWLiterals:
        """Build a generalized totalizer encoding for weighted literals.

        Args:
            wlits: The weighted literals (aperture.wlits) to build the generalized totalizer for.
            selector: An optional selector weighted literal that will be added to all clauses generated by the generalized totalizer. 
                      If None, no selector will be used.
            rhs_simplification: Simplifies the generalized totalizer (reducing the number of variables and clauses) 
                                based on the right-hand that should be the maximal value that will be bounded by the generalized totalizer
                                (usefull for bounding with < and <= constraints). If None, no simplification will be applied.
        Returns:
            Weighted literals (aperture.wlits) that encodes the weighted sum of the generalized totalizer.
            
        """
        ...
        
    @overload
    def add_constraint_less_than(self, lits: TLiterals, rhs: int, selector: Optional[TLit] = ...) -> bool:
        """Add a strict less-than cardinality constraint.

        Args:
            lits: The literals (aperture.lits) to build the constraint for.
            rhs: The right-hand side of the constraint.
            selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active.
        Returns:
            True if the constraint was added successfully, False if adding the constraint caused a conflict (i.e., the formula is unsatisfiable).
            
        """
        ...

    @overload
    def add_constraint_less_than_equal(self, lits: TLiterals, rhs: int, selector: Optional[TLit] = ...) -> bool:
        """Add a less-than-or-equal cardinality constraint.

        Args:
            lits: The literals (aperture.lits) to build the constraint for.
            rhs: The right-hand side of the constraint.
            selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active.
        Returns:
            True if the constraint was added successfully, False if adding the constraint caused a conflict (i.e., the formula is unsatisfiable).
            
        """
        ...

    @overload
    def add_constraint_equal(self, lits: TLiterals, rhs: int, selector: Optional[TLit] = ...) -> bool:
        """Add an equality cardinality constraint.

        Args:
            lits: The literals (aperture.lits) to build the constraint for.
            rhs: The right-hand side of the constraint.
             selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active.
            selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active.
        Returns:
            True if the constraint was added successfully, False if adding the constraint caused a conflict (i.e., the formula is unsatisfiable).
            
        """
        ...

    @overload
    def add_constraint_greater_than_equal(self, lits: TLiterals, rhs: int, selector: Optional[TLit] = ...) -> bool:
        """Add a greater-than-or-equal cardinality constraint.

        Args:
            lits: The literals (aperture.lits) to build the constraint for.
            rhs: The right-hand side of the constraint.
            selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active.
        Returns:
            True if the constraint was added successfully, False if adding the constraint caused a conflict (i.e., the formula is unsatisfiable).
            
        """
        ...

    @overload
    def add_constraint_greater_than(self, lits: TLiterals, rhs: int, selector: Optional[TLit] = ...) -> bool:
        """Add a strict greater-than cardinality constraint.

        Args:
            lits: The literals (aperture.lits) to build the constraint for.
            rhs: The right-hand side of the constraint.
             selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active.
            selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active.
        Returns:
            True if the constraint was added successfully, False if adding the constraint caused a conflict (i.e., the formula is unsatisfiable).
            
        """
        ...

    def add_constraint_less_than(self, wlits: TWLiterals, rhs: int, selector: Optional[TLit] = ...) -> bool:
        """Add a strict less-than pseudo-Boolean constraint.

        Args:
            wlits: The weighted literals (aperture.wlits) to build the constraint for.
            rhs: The right-hand side of the constraint.
            selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active.
        Returns:
            True if the constraint was added successfully, False if adding the constraint caused a conflict (i.e., the formula is unsatisfiable).
            
        """
        ...

    def add_constraint_less_than_equal(self, wlits: TWLiterals, rhs: int, selector: Optional[TLit] = ...) -> bool:
        """Add a less-than-or-equal pseudo-Boolean constraint.

        Args:
            wlits: The weighted literals (aperture.wlits) to build the constraint for. 
            rhs: The right-hand side of the constraint. 
            selector: An optional selector literal. If provided, the constraint will only be active when the selector is assumed False. 
            If None, the constraint will always be active. 
        Returns:
            True if the constraint was added successfully, False if adding the constraint caused a conflict (i.e., the formula is unsatisfiable).
        """
        ...

    def get_latest_maxsat_value(self) -> int:
        """Return the value of the latest MaxSAT query.
            
        Returns:
            The value of the solution of the latest MaxSAT query.
            
        """
        ...

    def is_latest_maxsat_optimal(self) -> bool:
        """Return whether the latest MaxSAT result is optimal.
            
        Returns:
            True if the latest MaxSAT query returned an optimal solution.
            
        """
        ...

    def is_latest_maxsat_fixed_model_value(self) -> bool:
        """Return whether the latest MaxSAT run fixed the model value.
            
        Returns:
            True if the latest MaxSAT query fixed the model value, False otherwise.
            This is only meaningful if the latest MaxSAT query was called with fix_model_value=True.
            
        """
        ...

    def solve_maxsat(self, assumptions: TLiterals, soft_lits: TLiterals, fix_model_value: bool, callback_on_solution_found: Optional[Callable[[TLiterals], bool]] = ...) -> bool:
        """Solve an unweighted MaxSAT instance.

        Args:
            assumptions: The assumptions (aperture.lits) to solve under.
            soft_lits: The soft literals (aperture.lits) to minimize SAT count for.
            fix_model_value: Whether to attempt to fix the latest solution's value.
            callback_on_solution_found: An optional callback function that will be called each time a new (improving) solution is found during the MaxSAT solving process.
            If the callback returns True, the MaxSAT solving process will be terminated, otherwise it will continue.
        Returns:
            True if the formula is satisfiable, otherwise False.
        """
        ...

    def solve_weighted_maxsat(self, assumptions: TLiterals, soft_wlits: TWLiterals, fix_model_value: bool, callback_on_solution_found: Optional[Callable[[TWLiterals], bool]] = ...) -> bool:
        """Solve a weighted MaxSAT instance.

        Args:
            assumptions: The assumptions (aperture.lits) to solve under. 
            soft_wlits: The soft weighted literals (aperture.wlits) to minimize weight (SAT) sum for. 
            fix_model_value: Whether to attempt to fix the latest solution's value.
            callback_on_solution_found: An optional callback function that will be called each time a new (improving) solution is found during the MaxSAT solving process.
            If the callback returns True, the MaxSAT solving process will be terminated, otherwise it will continue.
        Returns:
            True if the formula is satisfiable, otherwise False.
            
        """
        ...

    def get_latest_black_box_value(self) -> int:
        """Return the value of the latest black-box optimization query.

        Returns:
            The value of the solution of the latest black-box optimization query.
            
        """
        ...

    def solve_black_box(self, assumptions: TLiterals, observables: TLiterals, pb_func: Callable[[TLit], int], callback_on_solution_found: Optional[Callable[[TLiterals], bool]] = ...) -> bool:
        """Solve a black-box optimization query.

        Args:
            assumptions: The assumptions (aperture.lits) to solve under. 
            observables: The observable literals (aperture.lits) whose values will be passed to the pseudo-Boolean function to compute the objective value.
            pb_func: The pseudo-Boolean function to compute the objective value.
            callback_on_solution_found: An optional callback function that will be called each time a new (improving) solution is found during the black-box optimization process.
            If the callback returns True, the black-box optimization process will be terminated, otherwise it will continue.
        Returns:
            True if the formula is satisfiable, otherwise False.
        """
        ...

    def solve_obv(self, assumptions: TLiterals, targets: TLiterals, callback_on_solution_found: Optional[Callable[[TLiterals], bool]] = ...) -> bool:
        """Solve an OBV query.

        Args:
            assumptions: The assumptions (aperture.lits) to solve under.
            targets: The bit-vector literals (aperture.lits).
            callback_on_solution_found: An optional callback function that will be called each time a new (improving) solution is found during the OBV solving process.
            If the callback returns True, the OBV solving process will be terminated, otherwise it will continue.
        Returns:
            True if the formula is satisfiable, otherwise False.
        """
        ...


class lits(TLiterals): ...


class wlits(TWLiterals): ...


__all__ = ["Solver", "lits", "wlits", "TLit", "TLiterals", "TWLit", "TWLiterals"]
