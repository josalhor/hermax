#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <optional>
#include <vector>
#include "EvalMaxSAT.h"

namespace py = pybind11;

class EvalMaxSATLatest {
public:
    EvalMaxSAT<Solver_cadical> solver;
    int num_vars;

    EvalMaxSATLatest() : num_vars(0) {
#if defined(__APPLE__) && (defined(__aarch64__) || defined(__arm64__))
        // Mac arm64: avoid intermittent crashes in EvalMaxSAT local optimizer path.
        // Keep solver functionality by disabling only that optimization phase.
        solver.disableOptimize();
#endif
    }

    int newVar(bool decisionVar = true) {
        int v = solver.newVar(decisionVar);
        if (v > num_vars) num_vars = v;
        return v;
    }

    int addClause(const std::vector<int>& clause, std::optional<long long> weight = std::nullopt) {
        for (int lit : clause) {
            int v = std::abs(lit);
            if (v > num_vars) num_vars = v;
        }
        return solver.addClause(clause, weight);
    }

    bool solve() {
        return solver.solve();
    }

    long long getCost() {
        return (long long)solver.getCost();
    }

    bool getValue(int lit) {
        return solver.getValue(lit);
    }

    std::vector<int> getModel() {
        std::vector<int> model;
        // nVars() returns _poids.size()-1 which should be the total number of variables
        int n = solver.nVars();
        for (int i = 1; i <= n; ++i) {
            if (solver.getValue(i)) {
                model.push_back(i);
            } else {
                model.push_back(-i);
            }
        }
        return model;
    }

    void setNInputVars(unsigned int n) {
        solver.setNInputVars(n);
    }
};

PYBIND11_MODULE(evalmaxsat_latest, m) {
    m.doc() = "pybind11 plugin for EvalMaxSAT (Latest)";

    py::class_<EvalMaxSATLatest>(m, "EvalMaxSAT")
        .def(py::init<>())
        .def("newVar", &EvalMaxSATLatest::newVar, py::arg("decisionVar") = true)
        .def("addClause", &EvalMaxSATLatest::addClause, py::arg("clause"), py::arg("weight") = std::nullopt)
        .def("solve", &EvalMaxSATLatest::solve)
        .def("getCost", &EvalMaxSATLatest::getCost)
        .def("getValue", &EvalMaxSATLatest::getValue)
        .def("getModel", &EvalMaxSATLatest::getModel)
        .def("setNInputVars", &EvalMaxSATLatest::setNInputVars);
}
