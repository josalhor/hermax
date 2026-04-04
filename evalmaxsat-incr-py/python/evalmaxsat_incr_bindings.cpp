#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <string>
#include "../../EvalMaxSAT2022/ipamir.h"

namespace py = pybind11;

class EvalMaxSATIncr {
public:
    void* solver;

    EvalMaxSATIncr() : solver(ipamir_init()) {
        if (!solver) {
            throw std::runtime_error("Failed to initialize EvalMaxSATIncr solver.");
        }
    }

    ~EvalMaxSATIncr() {
        if (solver) {
            ipamir_release(solver);
            solver = nullptr;
        }
    }

    void addClause(const std::vector<int>& clause, std::optional<long long> weight = std::nullopt) {
        if (!weight.has_value()) {
            // Hard clause
            for (int lit : clause) {
                ipamir_add_hard(solver, lit);
            }
            ipamir_add_hard(solver, 0);
        } else {
            // IPAMIR only supports unit soft literals via add_soft_lit
            // For non-unit soft clauses, we follow the IPAMIR guidance:
            // introduce new literal b, add (C or b) as hard, declare b soft.
            if (clause.size() == 1) {
                // IPAMIR add_soft_lit(lit, w) means assigning 'lit' to true incurs cost 'w'.
                // Clarsify: adding unit soft clause [L] with weight W means if L is false (i.e., -L is true), cost W.
                // So we call ipamir_add_soft_lit(-L, W).
                ipamir_add_soft_lit(solver, -clause[0], (uint64_t)*weight);
            } else {
                throw std::runtime_error("EvalMaxSATIncr (IPAMIR) only supports unit soft clauses directly. Use add_soft_relaxed logic in Python.");
            }
        }
    }

    void addSoftLit(int lit, uint64_t weight) {
        ipamir_add_soft_lit(solver, lit, weight);
    }

    void assume(const std::vector<int>& assumptions) {
        for (int lit : assumptions) {
            ipamir_assume(solver, lit);
        }
    }

    int solve() {
        return ipamir_solve(solver);
    }

    uint64_t getCost() {
        return ipamir_val_obj(solver);
    }

    py::object getValue(int lit) {
        int val = ipamir_val_lit(solver, lit);
        if (val == lit) return py::cast(true);
        if (val == -lit) return py::cast(false);
        return py::none();
    }

    std::string signature() {
        return ipamir_signature();
    }
};

PYBIND11_MODULE(evalmaxsat_incr, m) {
    m.doc() = "pybind11 plugin for EvalMaxSATIncr (IPAMIR)";

    py::class_<EvalMaxSATIncr>(m, "EvalMaxSATIncr")
        .def(py::init<>())
        .def("addClause", &EvalMaxSATIncr::addClause, py::arg("clause"), py::arg("weight") = std::nullopt)
        .def("addSoftLit", &EvalMaxSATIncr::addSoftLit, py::arg("lit"), py::arg("weight"))
        .def("assume", &EvalMaxSATIncr::assume, py::arg("assumptions"))
        .def("solve", &EvalMaxSATIncr::solve)
        .def("getCost", &EvalMaxSATIncr::getCost)
        .def("getValue", &EvalMaxSATIncr::getValue, py::arg("lit"))
        .def("signature", &EvalMaxSATIncr::signature);
}
