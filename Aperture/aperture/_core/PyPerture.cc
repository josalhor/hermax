#include "PythonWrapper.h"

namespace nb = nanobind;

using namespace std;
using namespace Aperture;

const char* const __doc__ =
    "Pyperture: A Python interface for Aperture Solver.";

NB_MODULE(_aperture, m) {
  m.doc() = __doc__;

  nb::bind_vector<TLiterals>(m, "lits");
  nb::bind_vector<TWLiterals>(m, "wlits");

  nb::class_<AperturePython>(m, "Solver")
      .def(nb::init<const string&>(), nb::arg("sat_solver") = "glucose",
           "Initialize the solver with the specified SAT solver (default: "
           "'glucose').")
      .def("add_clause", &AperturePython::AddClause, nb::arg("clause"),
           "Add a clause to the solver.")
      .def("solve", &AperturePython::Solve,
           nb::arg("assumptions") = TLiterals(),
           "Solves the current formula under the specified assumptions.")
      .def("get_latest_solve_status", &AperturePython::GetLatestSolveStatus,
           "Get the status of the latest solve query.")
      .def("get_latest_solution", &AperturePython::GetLatestSolution,
           "Get the solution (model) of the latest solve query.")
      .def("new_var", &AperturePython::NewVar,
           "Creates a new variable in the solver. This is required before "
           "using variables in constraints / queries.")
      .def("max_var", &AperturePython::MaxVar,
           "Get the maximum variable created in the solver.")
      .def(
          "lit_value", &AperturePython::LitValue, nb::arg("lit"),
          "Get the value of a literal (positive for true, negative for false).")
      .def("get_verbosity_level", &AperturePython::GetVerbosityLevel,
           "Get the current verbosity level of the solver.")
      .def("set_verbosity_level", &AperturePython::SetVerbosityLevel,
           nb::arg("level"), "Set the verbosity level of the solver.")
      .def("set_enable_output_coloring",
           &AperturePython::SetEnableOutputColoring, nb::arg("enable"),
           "Enable or disable colored output in the solver's logs.")
      .def("get_latest_error_reason", &AperturePython::GetLatestErrorReason,
           "Get the reason for the latest error.")
      .def("set_param", &AperturePython::SetParam, nb::arg("param_name"),
           nb::arg("value"),
           "Set a parameter of the solver to a specified value.")
      .def(
          "get_totalizer", &AperturePython::GetTotalizer, nb::arg("lits"),
          nb::arg("selector"), nb::arg("rhs_simplification") = nb::none(),
          "Encodes a totalizer (cardinality) constraint for the given "
          "literals and returns the unary sum bits (literals). An optional "
          "selector literal can be provided and will be "
          "inserted into each auxiliary clause. If rhs_simplification is "
          "provided, the totalizer will be simplified (reduced clause count) "
          "with the given rhs value (usefull mainly for < and <= constraints).")
      .def(
          "get_gen_totalizer", &AperturePython::GetGenTotalizer,
          nb::arg("wlits"), nb::arg("selector"),
          nb::arg("rhs_simplification") = nb::none(),
          "Encodes a generalized totalizer (pseudo-Boolean) constraint for "
          "the given weighted literals and returns the unary sum bits "
          "(literals). An optional selector literal can be provided and will "
          "be "
          "inserted into each auxiliary clause. If rhs_simplification is "
          "provided, the totalizer will be simplified (reduced clause count) "
          "with the given rhs value (usefull mainly for < and <= constraints).")
      .def("add_constraint_less_than",
           nb::overload_cast<TLiterals&, uint64_t, optional<TLit>>(
               &AperturePython::AddConstraintLessThan),
           nb::arg("lits"), nb::arg("rhs"), nb::arg("selector") = nb::none(),
           "Add a less-than cardinality constraint (sum of lits < rhs) to the "
           "solver. An optional selector literal can be provided and will be "
           "inserted into each auxiliary clause.")
      .def("add_constraint_less_than_equal",
           nb::overload_cast<TLiterals&, uint64_t, optional<TLit>>(
               &AperturePython::AddConstraintLessThanEqual),
           nb::arg("lits"), nb::arg("rhs"), nb::arg("selector") = nb::none(),
           "Add a less-than-or-equal cardinality constraint (sum of lits <= "
           "rhs) to the solver. An optional selector literal can be provided "
           "and will be inserted into each auxiliary clause.")
      .def("add_constraint_equal", &AperturePython::AddConstraintEqual,
           nb::arg("lits"), nb::arg("rhs"), nb::arg("selector") = nb::none(),
           "Add an equality cardinality constraint (sum of lits = rhs) to the "
           "solver. An optional selector literal can be provided and will be "
           "inserted into each auxiliary clause.")
      .def("add_constraint_greater_than_equal",
           &AperturePython::AddConstraintGreaterThanEqual, nb::arg("lits"),
           nb::arg("rhs"), nb::arg("selector") = nb::none(),
           "Add a greater-than-or-equal cardinality constraint (sum of lits >= "
           "rhs) to the solver. An optional selector literal can be provided "
           "and will be inserted into each auxiliary clause.")
      .def("add_constraint_greater_than",
           &AperturePython::AddConstraintGreaterThan, nb::arg("lits"),
           nb::arg("rhs"), nb::arg("selector") = nb::none(),
           "Add a greater-than cardinality constraint (sum of lits > rhs) to "
           "the solver. An optional selector literal can be provided and will "
           "be inserted into each auxiliary clause.")
      .def("add_constraint_less_than",
           nb::overload_cast<TWLiterals&, uint64_t, optional<TLit>>(
               &AperturePython::AddConstraintLessThan),
           nb::arg("wlits"), nb::arg("rhs"), nb::arg("selector") = nb::none(),
           "Add a less-than cardinality constraint (sum of lit weights < rhs) "
           "to the solver. An optional selector literal can be provided and "
           "will be inserted into each auxiliary clause.")
      .def("add_constraint_less_than_equal",
           nb::overload_cast<TWLiterals&, uint64_t, optional<TLit>>(
               &AperturePython::AddConstraintLessThanEqual),
           nb::arg("wlits"), nb::arg("rhs"), nb::arg("selector") = nb::none(),
           "Add a less-than-or-equal cardinality constraint (sum of lit "
           "weights <= rhs) to the solver. An optional selector literal can be "
           "provided and will be inserted into each auxiliary clause.")
      .def("get_latest_maxsat_value", &AperturePython::GetLatestMaxSATValue,
           "Get the value of the latest MaxSAT query.")
      .def("is_latest_maxsat_optimal", &AperturePython::IsLatestMaxSATOptimal,
           "Returns true if the latest MaxSAT query was solved to optimality.")
      .def("is_latest_maxsat_fixed_model_value",
           &AperturePython::IsLatestMaxSATFixedModelValue,
           "Returns true if the latest MaxSAT query has a fixed model value, "
           "i.e. the solver was able to bound the latest value using clauses "
           "(e.g. during complete part algorithm).")
      .def("solve_maxsat", &AperturePython::SolveMaxSAT, nb::arg("assumptions"),
           nb::arg("soft_lits"), nb::arg("fix_model_value"),
           nb::arg("callback_on_solution_found") = nb::none(),
           "Solve a MaxSAT query with the given assumptions and soft literals. "
           "If a fixed model value is provided, the solver will attempt to "
           "bound the solution. An optional callback can be provided and will "
           "be called each time a new (improving) solution is found - if it "
           "returns true, the solving process will stop, otherwise it will "
           "continue.")
      .def("solve_weighted_maxsat", &AperturePython::SolveWeightedMaxSAT,
           nb::arg("assumptions"), nb::arg("soft_wlits"),
           nb::arg("fix_model_value"),
           nb::arg("callback_on_solution_found") = nb::none(),
           "Solve a Weighted MaxSAT query with the given assumptions and soft "
           "weighted literals. If a fixed model value is provided, the solver "
           "will attempt to bound the solution. An optional callback can be "
           "provided and will be called each time a new (improving) solution "
           "is found - if it returns true, the solving process will stop, "
           "otherwise it will continue.")
      .def("get_latest_black_box_value",
           &AperturePython::GetLatestBlackBoxValue,
           "Get the value of the latest black-box optimization query.")
      .def(
          "solve_black_box", &AperturePython::SolveBlackBox,
          nb::arg("assumptions"), nb::arg("observables"), nb::arg("pb_func"),
          nb::arg("callback_on_solution_found") = nb::none(),
          "Solve a black-box query with the given assumptions, observables and "
          "a pseudo-Boolean function (pb_func) provided as a callback "
          "black-box function. An optional callback can be provided and will "
          "be called each time a new (improving) solution is found - if it "
          "returns true, the solving process will stop, otherwise it will "
          "continue.")
      .def("solve_obv", &AperturePython::SolveOBV, nb::arg("assumptions"),
           nb::arg("targets"),
           nb::arg("callback_on_solution_found") = nb::none(),
           "Solve an OBV query with the given assumptions and target "
           "bit-vector (literals). An optional callback can be provided and "
           "will be called each time a new (improving) solution is found - if "
           "it returns true, the solving process will stop, otherwise it will "
           "continue.");
}
